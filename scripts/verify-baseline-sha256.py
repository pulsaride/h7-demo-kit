#!/usr/bin/env python3
"""Verify the self-referential SHA-256 of a baseline.json file.

The baseline uses a canonical SHA-256 computed over all fields except 'sha256'
itself, serialized with sorted keys and no whitespace (mirrors seed-offline-baseline.py).

Exit 0 on success, 1 on mismatch, 2 on usage error.
"""
import hashlib, json, sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify-baseline-sha256.py <baseline.json>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"[FAIL] baseline not found: {path}", file=sys.stderr)
        return 1

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[FAIL] invalid JSON in {path}: {e}", file=sys.stderr)
        return 1

    stored = doc.get("sha256", "")
    if not stored or stored == "pending":
        print(f"[FAIL] baseline not yet sealed (sha256={stored!r})")
        return 1

    def sorted_recursive(v):
        """Recursively sort dict keys — mirrors Rust BTreeMap serialization."""
        if isinstance(v, dict):
            return {k: sorted_recursive(vv) for k, vv in sorted(v.items())}
        return v

    # Three canonicalization approaches — try all:
    #
    # A) h7-sensor live calibration (Rust serde_json):
    #    set sha256="" placeholder, preserve field order from JSON file
    #
    # B) h7ctl / seed-offline-baseline.py (Rust BTreeMap / Python sort_keys):
    #    remove sha256, sort all keys recursively
    #
    # C) Python seed-offline-baseline.py legacy (sort_keys=True, flat):
    #    remove sha256, sort only top-level keys
    #
    doc_a = dict(doc); doc_a["sha256"] = ""
    digest_a = hashlib.sha256(
        json.dumps(doc_a, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    body_b = {k: sorted_recursive(v) for k, v in sorted(doc.items()) if k != "sha256"}
    digest_b = hashlib.sha256(
        json.dumps(body_b, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    body_c = {k: v for k, v in doc.items() if k != "sha256"}
    digest_c = hashlib.sha256(
        json.dumps(body_c, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    if stored == digest_a:
        method = "live-calibrated (Rust sha256='' placeholder, field order preserved)"
        digest = digest_a
    elif stored == digest_b:
        method = "offline-seeded (Rust BTreeMap / recursive sort_keys)"
        digest = digest_b
    elif stored == digest_c:
        method = "offline-seeded legacy (Python sort_keys, top-level only)"
        digest = digest_c
    else:
        print(f"[FAIL] SHA-256 mismatch on {path}")
        print(f"       stored       : {stored[:40]}…")
        print(f"       approach A   : {digest_a[:40]}…")
        print(f"       approach B   : {digest_b[:40]}…")
        print(f"       approach C   : {digest_c[:40]}…")
        return 1

    print(f"[OK]   baseline SHA-256 verified ({method})")
    print(f"       sha256   = {digest[:24]}…")
    print(f"       version  = {doc.get('version')}  mu_kappa = {doc.get('mu_kappa'):.4f}  n_ticks = {doc.get('n_ticks')}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
