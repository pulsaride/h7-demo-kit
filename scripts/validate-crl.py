#!/usr/bin/env python3
"""Validate a CRL (h7-cal/crl/v1) and optionally check if an issuer key is revoked.

Verifies:
- Schema and required fields
- CRL is not expired (valid_until > now)
- Ed25519 signature over canonical body
- Optionally: whether a given issuer_key_id appears in revocations

Usage:
  # Validate CRL integrity only
  python3 scripts/validate-crl.py --crl run/crl.json --pub-key run/keys/h7-crl-signer.pub

  # Check if a key is revoked
  python3 scripts/validate-crl.py --crl run/crl.json --pub-key run/keys/h7-crl-signer.pub \\
      --check-key-id "h7-cert-issuer-abc123"

Exit code: 0 = valid (and not revoked if --check-key-id given)
           1 = validation error or key is revoked
           2 = usage error
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
except ImportError:
    raise SystemExit("Missing dependency: pip install cryptography")

SCHEMA = "h7-cal/crl/v1"
REQUIRED_BODY_FIELDS = {"schema", "issued_at", "valid_until", "crl_signing_key_id", "revocations"}


def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_pub_key(pub_path: Path) -> Ed25519PublicKey:
    raw_hex = pub_path.read_text().strip()
    pub_bytes = bytes.fromhex(raw_hex)
    return Ed25519PublicKey.from_public_bytes(pub_bytes)


def validate(crl_path: Path, pub_path: Path, check_key_id: str | None = None) -> int:
    # --- Load CRL ---
    try:
        crl = json.loads(crl_path.read_text())
    except Exception as exc:
        print(f"[validate-crl] ERROR: cannot parse CRL: {exc}", file=sys.stderr)
        return 1

    body = crl.get("body")
    sig_b64 = crl.get("sig_b64")

    if not body or not sig_b64:
        print("[validate-crl] ERROR: missing 'body' or 'sig_b64' in CRL", file=sys.stderr)
        return 1

    # --- Required fields ---
    missing = REQUIRED_BODY_FIELDS - set(body.keys())
    if missing:
        print(f"[validate-crl] ERROR: missing body fields: {sorted(missing)}", file=sys.stderr)
        return 1

    if body["schema"] != SCHEMA:
        print(f"[validate-crl] ERROR: unexpected schema {body['schema']!r}", file=sys.stderr)
        return 1

    # --- Expiry ---
    try:
        valid_until = datetime.fromisoformat(body["valid_until"].rstrip("Z")).replace(tzinfo=timezone.utc)
    except Exception as exc:
        print(f"[validate-crl] ERROR: cannot parse valid_until: {exc}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    if now > valid_until:
        print(f"[validate-crl] ERROR: CRL expired at {body['valid_until']}", file=sys.stderr)
        return 1

    # --- Signature ---
    try:
        pub_key = _load_pub_key(pub_path)
    except Exception as exc:
        print(f"[validate-crl] ERROR: cannot load public key: {exc}", file=sys.stderr)
        return 1

    try:
        sig = base64.b64decode(sig_b64)
        pub_key.verify(sig, _canonical(body))
    except InvalidSignature:
        print("[validate-crl] ERROR: INVALID SIGNATURE — CRL has been tampered", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[validate-crl] ERROR: signature verification failed: {exc}", file=sys.stderr)
        return 1

    days_left = (valid_until - now).days
    print(f"[validate-crl] ✓ signature valid")
    print(f"  schema       : {body['schema']}")
    print(f"  issued_at    : {body['issued_at']}")
    print(f"  valid_until  : {body['valid_until']} ({days_left} days left)")
    print(f"  revocations  : {len(body['revocations'])}")

    # --- Check specific key ---
    if check_key_id:
        revoked_entry = next(
            (r for r in body["revocations"] if r.get("issuer_key_id") == check_key_id),
            None,
        )
        if revoked_entry:
            print(f"[validate-crl] ✗ KEY REVOKED: {check_key_id!r}")
            print(f"  revoked_at  : {revoked_entry.get('revoked_at')}")
            print(f"  reason      : {revoked_entry.get('reason')}")
            if revoked_entry.get("incident_ref"):
                print(f"  incident    : {revoked_entry['incident_ref']}")
            return 1
        else:
            print(f"[validate-crl] ✓ key not revoked: {check_key_id!r}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--crl", type=Path, required=True, help="Path to CRL JSON file")
    parser.add_argument("--pub-key", type=Path, required=True,
                        help="Path to CRL signer public key (hex, run/keys/h7-crl-signer.pub)")
    parser.add_argument("--check-key-id", default=None,
                        help="issuer_key_id to check for revocation")
    args = parser.parse_args()

    if not args.crl.is_file():
        print(f"[validate-crl] ERROR: CRL file not found: {args.crl}", file=sys.stderr)
        return 2
    if not args.pub_key.is_file():
        print(f"[validate-crl] ERROR: public key not found: {args.pub_key}", file=sys.stderr)
        return 2

    return validate(args.crl, args.pub_key, args.check_key_id)


if __name__ == "__main__":
    raise SystemExit(main())
