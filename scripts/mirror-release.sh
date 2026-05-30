#!/usr/bin/env bash
# Mirror a signed Release from a private upstream repo (pulsaride/p-h7) to
# the public h7-demo-kit Releases, so third-party testers can fetch binaries
# anonymously without source access.
#
# Usage:
#   bash scripts/mirror-release.sh <TAG>
#   TAG=v0.7.2 bash scripts/mirror-release.sh
#
# Env (optional):
#   UPSTREAM_REPO   default: pulsaride/p-h7
#   PUBLIC_REPO     default: pulsaride/h7-demo-kit
#
# Requirements: gh CLI authenticated with read access to UPSTREAM_REPO and
# write access to PUBLIC_REPO; openssl; pinned pubkey at
# fixtures/H7_RELEASE_SIGNING.pub for signature self-check.

set -euo pipefail

TAG="${1:-${TAG:-}}"
if [[ -z "$TAG" ]]; then
  echo "usage: $0 <TAG>     (e.g. $0 v0.7.2)" >&2
  exit 2
fi

UPSTREAM_REPO="${UPSTREAM_REPO:-pulsaride/p-h7}"
PUBLIC_REPO="${PUBLIC_REPO:-pulsaride/h7-demo-kit}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PINNED_PUBKEY="${SCRIPT_DIR}/../fixtures/H7_RELEASE_SIGNING.pub"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

echo "[mirror] downloading $TAG from $UPSTREAM_REPO"
gh release download "$TAG" --repo "$UPSTREAM_REPO" \
  --pattern "h7-x86_64-unknown-linux-musl.tar.gz" \
  --pattern "h7-sensor-x86_64-unknown-linux-musl.tar.gz" \
  --pattern "h7-aarch64-unknown-linux-musl.tar.gz" \
  --pattern "SHA256SUMS" \
  --pattern "SHA256SUMS.sig" \
  --pattern "H7_RELEASE_SIGNING.pub"

echo "[mirror] verifying signature with pinned pubkey"
if [[ ! -f "$PINNED_PUBKEY" ]]; then
  echo "[mirror] ERROR: pinned pubkey missing at $PINNED_PUBKEY" >&2
  exit 3
fi
if ! diff -q "$PINNED_PUBKEY" H7_RELEASE_SIGNING.pub >/dev/null; then
  echo "[mirror] ERROR: upstream H7_RELEASE_SIGNING.pub differs from pinned key!" >&2
  echo "[mirror] Refusing to mirror — investigate key rotation before continuing." >&2
  exit 4
fi
openssl pkeyutl -verify -pubin -inkey H7_RELEASE_SIGNING.pub \
  -rawin -in SHA256SUMS -sigfile SHA256SUMS.sig

echo "[mirror] verifying tarball checksums"
# Upstream SHA256SUMS contains multi-platform assets (mac/windows) that this
# mirror does not download. Validate only the linux artifacts we publish.
grep -E ' (h7-x86_64-unknown-linux-musl\.tar\.gz|h7-sensor-x86_64-unknown-linux-musl\.tar\.gz|h7-aarch64-unknown-linux-musl\.tar\.gz)$' \
  SHA256SUMS > SHA256SUMS.linux
sha256sum -c SHA256SUMS.linux

echo "[mirror] publishing $TAG to $PUBLIC_REPO"
gh release create "$TAG" \
  --repo "$PUBLIC_REPO" \
  --title "${TAG} — Demo Kit Binaries (mirrored from ${UPSTREAM_REPO})" \
  --notes "Public mirror of signed h7 + h7-sensor binaries from ${UPSTREAM_REPO} ${TAG}.

Source code remains in ${UPSTREAM_REPO} (private).
Binaries are signed with the Ed25519 key pinned in fixtures/H7_RELEASE_SIGNING.pub.

Verification:
  openssl pkeyutl -verify -pubin -inkey H7_RELEASE_SIGNING.pub \\
    -rawin -in SHA256SUMS -sigfile SHA256SUMS.sig
  sha256sum -c SHA256SUMS

Usage:
  make setup
  make calibrate
  make up
  make attack-vercel
  make verify-alert" \
  h7-x86_64-unknown-linux-musl.tar.gz \
  h7-sensor-x86_64-unknown-linux-musl.tar.gz \
  h7-aarch64-unknown-linux-musl.tar.gz \
  SHA256SUMS \
  SHA256SUMS.sig \
  H7_RELEASE_SIGNING.pub

echo "[mirror] ✓ $TAG mirrored: https://github.com/${PUBLIC_REPO}/releases/tag/${TAG}"
