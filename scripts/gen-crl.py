#!/usr/bin/env python3
"""Generate a signed CRL (Certificate Revocation List) — schema h7-cal/crl/v1.

Design from ADR-PROD-008. The CRL is a JSON document signed with a dedicated
Ed25519 CRL-signer key (distinct from the cert-issuer key). For demo/pilot use,
the signer key is loaded from the local key directory.

Usage:
  # Create/update CRL (starts empty, adds revocation entries from --revoke)
  python3 scripts/gen-crl.py \\
      --keys-dir  run/keys \\
      --out       run/crl.json \\
      --valid-days 90

  # Add a revocation entry
  python3 scripts/gen-crl.py \\
      --keys-dir  run/keys \\
      --out       run/crl.json \\
      --revoke    "h7-cert-issuer-abc123" \\
      --reason    key_compromise \\
      --incident  "PULSARIDE-INC-2026-001"
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption, load_pem_private_key,
    )
except ImportError:
    raise SystemExit("Missing dependency: pip install cryptography")

SCHEMA = "h7-cal/crl/v1"
REASON_CODES = {"unspecified", "key_compromise", "superseded", "cessation_of_operation"}

# Key file names for the CRL signer (separate from cert-issuer)
_CRL_SIGNER_PEM = "h7-crl-signer.pem"
_CRL_SIGNER_PUB = "h7-crl-signer.pub"


def _load_or_generate_crl_signer(keys_dir: Path) -> tuple[Ed25519PrivateKey, bytes]:
    priv_path = keys_dir / _CRL_SIGNER_PEM
    pub_path = keys_dir / _CRL_SIGNER_PUB
    if priv_path.exists():
        with open(priv_path, "rb") as f:
            priv = load_pem_private_key(f.read(), password=None)
        pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return priv, pub
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    keys_dir.mkdir(parents=True, exist_ok=True)
    with open(priv_path, "wb") as f:
        f.write(priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    priv_path.chmod(0o600)
    pub_path.write_text(pub.hex())
    print(f"[gen-crl] Generated CRL signer key → {priv_path}")
    print("[gen-crl] NOTE: In production, this key must be stored in an HSM (dual-control).")
    return priv, pub


def _key_id(pub: bytes) -> str:
    import hashlib
    return "h7-crl-signer-" + hashlib.sha256(pub).hexdigest()[:16]


def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(body: dict, priv: Ed25519PrivateKey) -> str:
    sig = priv.sign(_canonical(body))
    return base64.b64encode(sig).decode()


def _load_crl(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        crl = json.loads(path.read_text())
        if crl.get("body", {}).get("schema") != SCHEMA:
            print(f"[gen-crl] WARNING: existing file has unexpected schema; overwriting.", file=sys.stderr)
            return None
        return crl
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keys-dir", type=Path, default=Path("run/keys"))
    parser.add_argument("--out", type=Path, default=Path("run/crl.json"))
    parser.add_argument("--valid-days", type=int, default=90)
    parser.add_argument("--revoke", metavar="ISSUER_KEY_ID", default=None,
                        help="issuer_key_id to add to the revocation list")
    parser.add_argument("--reason", choices=sorted(REASON_CODES), default="unspecified")
    parser.add_argument("--incident", default=None, metavar="REF",
                        help="Incident reference (e.g. PULSARIDE-INC-2026-001)")
    args = parser.parse_args()

    priv, pub = _load_or_generate_crl_signer(args.keys_dir)
    signer_id = _key_id(pub)

    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(days=args.valid_days)

    existing = _load_crl(args.out)
    revocations: list[dict] = []
    if existing:
        revocations = existing.get("body", {}).get("revocations", [])

    if args.revoke:
        entry = {
            "issuer_key_id": args.revoke,
            "revoked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason": args.reason,
            "revocation_authority": "h7-crl-operator",
        }
        if args.incident:
            entry["incident_ref"] = args.incident
        existing_ids = {r["issuer_key_id"] for r in revocations}
        if args.revoke in existing_ids:
            print(f"[gen-crl] WARNING: {args.revoke!r} already in CRL — updating entry", file=sys.stderr)
            revocations = [r for r in revocations if r["issuer_key_id"] != args.revoke]
        revocations.append(entry)
        print(f"[gen-crl] Added revocation for {args.revoke!r} (reason: {args.reason})")

    body = {
        "schema": SCHEMA,
        "issued_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "valid_until": valid_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "crl_signing_key_id": signer_id,
        "revocations": revocations,
    }

    crl = {
        "body": body,
        "sig_b64": _sign(body, priv),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(crl, indent=2) + "\n")
    print(f"[gen-crl] CRL written → {args.out}")
    print(f"  revocations : {len(revocations)}")
    print(f"  valid until : {valid_until.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print(f"  signer id   : {signer_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
