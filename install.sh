#!/usr/bin/env bash
# Pulsaride H7 — one-line installer
#
#   curl -sSL https://raw.githubusercontent.com/pulsaride/h7-demo-kit/main/install.sh | sudo bash
#
# Requirements: Debian/Ubuntu amd64, systemd, curl
# Installs:     /usr/bin/h7-sensor  (eBPF sensor daemon)
#               /usr/bin/h7ctl      (operator CLI)
# Post-install: systemd unit enabled (not started), Ed25519 issuer key generated,
#               H7_API_TOKEN written to /etc/pulsaride-h7/brain.env (0640)

set -euo pipefail

REPO="pulsaride/h7-demo-kit"
REQUIRED_ARCH="amd64"
MIN_UBUNTU="20.04"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BOLD='\033[1m'; NC='\033[0m'

die()  { echo -e "${RED}error:${NC} $*" >&2; exit 1; }
warn() { echo -e "${YELLOW}warn:${NC}  $*" >&2; }
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
info() { echo -e "${BOLD}[→]${NC} $*"; }

# ── sanity checks ──────────────────────────────────────────────────────────────

[[ $EUID -eq 0 ]] || die "run as root (sudo bash install.sh)"

[[ "$(uname -s)" == "Linux" ]] || die "H7 requires Linux"

ARCH=$(dpkg --print-architecture 2>/dev/null) \
    || die "dpkg not found — Debian/Ubuntu required"
[[ "$ARCH" == "$REQUIRED_ARCH" ]] \
    || die "H7 sensor requires x86_64 (amd64); detected: $ARCH"

if ! command -v systemctl &>/dev/null; then
    die "systemd not found — H7 requires a systemd host"
fi

if ! command -v curl &>/dev/null; then
    apt-get install -y --no-install-recommends curl 2>/dev/null \
        || die "curl not found and cannot install it"
fi

# ── fetch latest release metadata ─────────────────────────────────────────────

info "Fetching latest H7 release from GitHub…"

RELEASE_JSON=$(curl -sSf "https://api.github.com/repos/${REPO}/releases/latest") \
    || die "cannot reach GitHub API (check network / firewall)"

VERSION=$(printf '%s' "$RELEASE_JSON" \
    | grep -o '"tag_name": "[^"]*"' | head -1 | cut -d'"' -f4)
[[ -n "$VERSION" ]] || die "could not parse release tag from GitHub API"

DEB_URL=$(printf '%s' "$RELEASE_JSON" \
    | grep -o '"browser_download_url": "[^"]*_amd64\.deb"' \
    | head -1 | cut -d'"' -f4)
[[ -n "$DEB_URL" ]] || die "no _amd64.deb asset found in release $VERSION"

SHA_URL=$(printf '%s' "$RELEASE_JSON" \
    | grep -o '"browser_download_url": "[^"]*SHA256SUMS\.deb"' \
    | head -1 | cut -d'"' -f4)

DEB_NAME=$(basename "$DEB_URL")

info "Version : $VERSION"
info "Package : $DEB_NAME"

# ── download ───────────────────────────────────────────────────────────────────

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

info "Downloading…"
curl -sSfL "$DEB_URL" -o "$TMPDIR/$DEB_NAME"

# ── verify SHA256 (skip gracefully if no checksum asset) ──────────────────────

if [[ -n "$SHA_URL" ]]; then
    curl -sSfL "$SHA_URL" -o "$TMPDIR/SHA256SUMS.deb"
    EXPECTED=$(grep "$DEB_NAME" "$TMPDIR/SHA256SUMS.deb" | awk '{print $1}')
    if [[ -n "$EXPECTED" ]]; then
        ACTUAL=$(sha256sum "$TMPDIR/$DEB_NAME" | awk '{print $1}')
        if [[ "$EXPECTED" == "$ACTUAL" ]]; then
            ok "SHA256 verified"
        else
            die "SHA256 mismatch!\n  expected: $EXPECTED\n  actual:   $ACTUAL"
        fi
    else
        warn "package not found in SHA256SUMS.deb — skipping verification"
    fi
else
    warn "no SHA256SUMS.deb asset in this release — skipping verification"
fi

# ── install ────────────────────────────────────────────────────────────────────

info "Installing pulsaride-h7 ${VERSION}…"
# --force-confmiss: restore conffiles deleted by the admin (e.g. after h7-uninstall.sh).
# Without this flag dpkg silently skips conffiles it believes were intentionally removed.
dpkg -i --force-confmiss "$TMPDIR/$DEB_NAME"

# ── post-install instructions ─────────────────────────────────────────────────

echo ""
echo -e "${BOLD}==================================================================${NC}"
echo -e "${GREEN}  H7 ${VERSION} installed successfully${NC}"
echo -e "${BOLD}==================================================================${NC}"
echo ""
echo "  Next steps:"
echo ""
echo "    1. Run preflight check:"
echo "         sudo h7ctl doctor"
echo ""
echo "    2. Calibrate the behavioral baseline (run on an idle system):"
echo "         sudo h7ctl calibrate"
echo ""
echo "    3. Deploy the brain + monitor:"
echo "         sudo h7ctl deploy"
echo ""
echo "    4. Start the sensor:"
echo "         sudo systemctl start pulsaride-h7"
echo ""
echo "    5. Check status:"
echo "         sudo systemctl status pulsaride-h7"
echo "         sudo h7ctl status"
echo ""
echo "  Ghost Mode (headless, no TCP port):"
echo "    docker compose -f /etc/pulsaride-h7/compose.ghost.yml up -d"
echo ""
echo "  API token (required for all brain API calls):"
echo "    sudo cat /etc/pulsaride-h7/brain.env"
echo ""
