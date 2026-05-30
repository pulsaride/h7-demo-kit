#!/usr/bin/env bash
# Download precompiled h7 + h7-sensor binaries from GitHub Releases.
# Public demo-kit helper: no private source checkout required.

set -euo pipefail

OUT_DIR="${1:-}"
if [[ -z "$OUT_DIR" ]]; then
  echo "usage: $0 <out_dir>" >&2
  exit 2
fi

# Skip download if both binaries already present (idempotent re-runs / offline demo)
if [[ -x "${OUT_DIR}/h7" && -x "${OUT_DIR}/h7-sensor" && "${H7_SKIP_FETCH:-0}" != "0" ]]; then
  echo "[fetch] H7_SKIP_FETCH=1 and binaries already present in ${OUT_DIR} — skipping download"
  exit 0
fi

REPO="${H7_RELEASE_REPO:-pulsaride/h7-demo-kit}"
RELEASE_TAG="${H7_RELEASE_TAG:-latest}"
BASE_URL="https://github.com/${REPO}/releases"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Trust anchor (mandatory): local pinned public key file.
# Fail closed if the key is missing: never trust a key downloaded from the network.
PINNED_PUBKEY_FILE="${H7_RELEASE_SIGNING_PUBKEY_FILE:-${SCRIPT_DIR}/../fixtures/H7_RELEASE_SIGNING.pub}"

if [[ ! -f "$PINNED_PUBKEY_FILE" ]]; then
  echo "[fetch] REFUS: pinned release signing key not found: ${PINNED_PUBKEY_FILE}" >&2
  echo "[fetch] The demo kit runs in fail-closed mode and refuses network-trusted keys." >&2
  echo "[fetch] Provide H7_RELEASE_SIGNING_PUBKEY_FILE pointing to a local H7_RELEASE_SIGNING.pub." >&2
  exit 2
fi

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64) target="x86_64-unknown-linux-musl" ;;
  aarch64|arm64) target="aarch64-unknown-linux-musl" ;;
  *)
    echo "Unsupported architecture: ${arch}. Set H7_TARGET manually." >&2
    exit 2
    ;;
esac
if [[ -n "${H7_TARGET:-}" ]]; then
  target="$H7_TARGET"
fi

mkdir -p "$OUT_DIR"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

if [[ "$RELEASE_TAG" == "latest" ]]; then
  release_url="${BASE_URL}/latest/download"
else
  release_url="${BASE_URL}/download/${RELEASE_TAG}"
fi

h7_archive="h7-${target}.tar.gz"
sensor_archive="h7-sensor-${target}.tar.gz"
checksums_url="${release_url}/SHA256SUMS"
checksums_sig_url="${release_url}/SHA256SUMS.sig"

echo "[fetch] repo=${REPO} tag=${RELEASE_TAG} target=${target}"
echo "[fetch] downloading ${h7_archive}"
curl -fsSL "${release_url}/${h7_archive}" -o "${workdir}/${h7_archive}"

echo "[fetch] downloading ${sensor_archive}"
curl -fsSL "${release_url}/${sensor_archive}" -o "${workdir}/${sensor_archive}"

echo "[fetch] downloading SHA256SUMS + SHA256SUMS.sig"
curl -fsSL "$checksums_url" -o "${workdir}/SHA256SUMS"
curl -fsSL "$checksums_sig_url" -o "${workdir}/SHA256SUMS.sig"

echo "[fetch] using pinned release signing public key: $PINNED_PUBKEY_FILE"
cp "$PINNED_PUBKEY_FILE" "${workdir}/H7_RELEASE_SIGNING.pub"

echo "[fetch] verifying SHA256SUMS.sig (Ed25519)"
if ! openssl pkeyutl -verify -rawin -pubin \
  -inkey "${workdir}/H7_RELEASE_SIGNING.pub" \
  -in "${workdir}/SHA256SUMS" \
  -sigfile "${workdir}/SHA256SUMS.sig" >/dev/null; then
  echo "[fetch] REFUS: SHA256SUMS.sig verification failed with pinned key." >&2
  echo "[fetch] Expected key: ${PINNED_PUBKEY_FILE}" >&2
  exit 2
fi

echo "[fetch] verifying checksums for downloaded archives"
(
  cd "$workdir"
  grep " ${h7_archive}$" SHA256SUMS | sha256sum -c -
  grep " ${sensor_archive}$" SHA256SUMS | sha256sum -c -
)

tar -xzf "${workdir}/${h7_archive}" -C "$workdir"
tar -xzf "${workdir}/${sensor_archive}" -C "$workdir"

if [[ ! -f "${workdir}/h7" ]]; then
  echo "[fetch] missing h7 binary in archive ${h7_archive}" >&2
  exit 2
fi
if [[ ! -f "${workdir}/h7-sensor" ]]; then
  echo "[fetch] missing h7-sensor binary in archive ${sensor_archive}" >&2
  exit 2
fi

install -m 0755 "${workdir}/h7" "${OUT_DIR}/h7"
install -m 0755 "${workdir}/h7-sensor" "${OUT_DIR}/h7-sensor"

echo "[fetch] installed: ${OUT_DIR}/h7"
echo "[fetch] installed: ${OUT_DIR}/h7-sensor"