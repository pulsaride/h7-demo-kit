#!/usr/bin/env python3
"""Seed an offline baseline when /sys/kernel/btf/vmlinux is absent.

Reads a pinned local fixture (no network), computes a deterministic SHA-256
self-reference, and writes run/baseline.json so that `make up` accepts the
calibration state (sha256 != "pending").

Fail-closed: refuses to run if the pinned fixture is missing. Never fetches
fallback assets from the network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_SHA_KEY = "sha256"


def _canonical_bytes(doc: dict) -> bytes:
    """Canonical encoding excluding the sha256 self-reference."""
    body = {k: v for k, v in doc.items() if k != _SHA_KEY}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True,
                        help="Pinned baseline fixture (local, no network).")
    parser.add_argument("--output", type=Path, required=True,
                        help="Destination baseline path (e.g. run/baseline.json).")
    args = parser.parse_args()

    if not args.fixture.is_file():
        print(f"[seed-offline-baseline] REFUS: pinned fixture missing: {args.fixture}",
              file=sys.stderr)
        print("[seed-offline-baseline] No network fallback is permitted (Zero-Trust).",
              file=sys.stderr)
        return 2

    try:
        doc = json.loads(args.fixture.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[seed-offline-baseline] REFUS: fixture is not valid JSON: {exc}",
              file=sys.stderr)
        return 2
    if not isinstance(doc, dict):
        print("[seed-offline-baseline] REFUS: fixture root must be a JSON object",
              file=sys.stderr)
        return 2

    digest = hashlib.sha256(_canonical_bytes(doc)).hexdigest()
    doc[_SHA_KEY] = digest
    doc["calibration_source"] = "offline-fallback"
    doc["btf_available"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"[seed-offline-baseline] wrote {args.output} (sha256={digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
