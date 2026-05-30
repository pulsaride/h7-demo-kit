#!/usr/bin/env bash
# Offline attestation verifier — no network required after download.
#
# Usage:
#   ./scripts/verify-attest.sh <path-to.cbor> <pub_key_hex>
#   ./scripts/verify-attest.sh <path-to.cbor>
#       → pub_key_hex auto-loaded from h7-monitor backend key store
#
# The .cbor file is the packed H7-QR envelope (base64url-decoded from /attest/…/cbor).
# Requires: python3, cbor2, cryptography (auto-installed if absent).

set -euo pipefail

CBOR_FILE="${1:-}"
PUB_HEX="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KIT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default backend key dir (can be overridden via H7_KEYS_DIR)
H7_KEYS_DIR="${H7_KEYS_DIR:-$KIT_ROOT/../h7-monitor/backend/.h7_keys}"

if [[ -z "$CBOR_FILE" ]]; then
  echo "Usage: $0 <attestation.cbor> [pub_key_hex]" >&2
  exit 1
fi

if [[ ! -f "$CBOR_FILE" ]]; then
  echo "[error] CBOR file not found: $CBOR_FILE" >&2
  exit 1
fi

# Resolve public key: argument → key store file → error
if [[ -z "$PUB_HEX" ]]; then
  PUB_FILE="$H7_KEYS_DIR/h7_signing.pub"
  if [[ -f "$PUB_FILE" ]]; then
    PUB_HEX="$(cat "$PUB_FILE")"
    echo "[info] public key loaded from $PUB_FILE"
  else
    echo "[error] no pub_key_hex provided and $PUB_FILE not found." >&2
    echo "        Either run 'make e2e-full' first (generates keys), or pass pub_key_hex as \$2." >&2
    echo "        The pub_key is also shown in the /attest/[id] UI page." >&2
    exit 1
  fi
fi

# Auto-install cbor2 + cryptography if absent
python3 -c "import cbor2, cryptography" 2>/dev/null || {
  echo "[info] installing cbor2 + cryptography (one-time)…"
  pip install --quiet cbor2 cryptography
}

echo "[verify] cbor  : $CBOR_FILE ($(wc -c < "$CBOR_FILE") bytes)"
echo "[verify] pubkey: ${PUB_HEX:0:16}…${PUB_HEX: -8}"
echo ""

python3 - "$CBOR_FILE" "$PUB_HEX" <<'PYEOF'
"""
H7-QR envelope verification.

Envelope layout (CBOR map with integer keys):
  0  version    str   "H7-QR/1.1"
  1  hash       bytes sha256 of entity state
  2  kappa      bytes 4-byte big-endian float32
  3  nr_running uint8
  4  ts         uint32 unix timestamp
  5  status     uint8  0=NOMINAL 1=WARNING 2=ALERT 3=BREACH
  6  sig_id     bytes(6) first 6 bytes of public key
  7  signature  bytes(64) Ed25519 over canonical(keys 0-6)

Verification: reconstruct canonical = cbor2.dumps({0..6}, canonical=True)
and verify signature against it.
"""
import sys, struct, cbor2
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

STATUS_LABELS = {0: "NOMINAL", 1: "WARNING", 2: "ALERT", 3: "BREACH"}
K_SIGNATURE = 7

cbor_path = sys.argv[1]
pub_hex = sys.argv[2].strip()

with open(cbor_path, "rb") as f:
    envelope = cbor2.loads(f.read())

if not isinstance(envelope, dict):
    print("[FAIL] unexpected CBOR structure (expected map)")
    sys.exit(1)

sig_bytes = envelope.get(K_SIGNATURE)
if sig_bytes is None or len(sig_bytes) != 64:
    print(f"[FAIL] signature field missing or wrong length ({len(sig_bytes) if sig_bytes else 0} bytes)")
    sys.exit(1)

# Reconstruct the canonical payload (keys 0-6, same encoding as at signing time)
canonical_map = {k: v for k, v in envelope.items() if k != K_SIGNATURE}
canonical_bytes = cbor2.dumps(canonical_map, canonical=True, timezone=None)

pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex))

# Cross-check sig_id fingerprint
sig_id = envelope.get(6, b"")
pub_bytes = bytes.fromhex(pub_hex)
if sig_id and sig_id != pub_bytes[:6]:
    print(f"[WARN] sig_id fingerprint mismatch — key may be wrong")
    print(f"       envelope sig_id : {sig_id.hex()}")
    print(f"       pubkey prefix   : {pub_bytes[:6].hex()}")

try:
    pub.verify(sig_bytes, canonical_bytes)
except Exception as e:
    print(f"[FAIL] Signature INVALID: {e}")
    sys.exit(1)

# Decode fields for display
kappa_bytes = envelope.get(2, b"\x00\x00\x00\x00")
kappa = struct.unpack(">f", kappa_bytes)[0] if isinstance(kappa_bytes, (bytes, bytearray)) else float(kappa_bytes)
ts = envelope.get(4, 0)
status_int = envelope.get(5, 0)
status_str = STATUS_LABELS.get(status_int, f"?({status_int})")
from datetime import datetime, timezone
ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "?"

print("┌─────────────────────────────────────────────┐")
print("│  ✓  ATTESTATION VALID  (Ed25519)            │")
print("└─────────────────────────────────────────────┘")
print(f"  version   : {envelope.get(0, '?')}")
print(f"  status    : {status_str}")
print(f"  kappa     : {kappa:.6f}")
print(f"  timestamp : {ts_str}")
print(f"  sig_id    : {sig_id.hex() if sig_id else '?'}")
print(f"  hash      : {envelope.get(1, b'').hex()[:32]}…")
PYEOF
