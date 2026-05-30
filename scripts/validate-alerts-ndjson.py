#!/usr/bin/env python3
"""
validate-alerts-ndjson.py \u2014 contract test for run/logs/alerts.ndjson.

Reads every line of an NDJSON alert stream, validates each event against
the frozen JSON schema (docs/schemas/alert-v1.1.json). Exit 0 if all
lines pass, 1 otherwise. Used by `make verify` and by CI.

Dependency: jsonschema (stdlib fallback if absent: minimal manual checks).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_manual(event: dict, schema: dict) -> list[str]:
    """Fallback validator (no jsonschema dep): required fields + const + enum."""
    errs: list[str] = []
    required = schema.get("required", [])
    for k in required:
        if k not in event:
            errs.append(f"missing required field: {k}")
    props = schema.get("properties", {})
    for k, v in event.items():
        if k not in props:
            errs.append(f"unknown field: {k}")
            continue
        spec = props[k]
        if "const" in spec and v != spec["const"]:
            errs.append(f"{k}: expected const {spec['const']!r}, got {v!r}")
        if "enum" in spec and v not in spec["enum"]:
            errs.append(f"{k}: value {v!r} not in {spec['enum']!r}")
    return errs


def main() -> int:
    p = argparse.ArgumentParser(description="Validate alerts.ndjson against frozen schema.")
    p.add_argument("ndjson", type=Path, help="Path to alerts.ndjson")
    p.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).parent.parent / "docs" / "schemas" / "alert-v1.1.json",
    )
    args = p.parse_args()

    if not args.ndjson.exists():
        print(f"[validate] {args.ndjson} absent", file=sys.stderr)
        return 1
    schema = _load_schema(args.schema)

    try:
        from jsonschema import Draft202012Validator  # type: ignore

        validator = Draft202012Validator(schema)
        use_lib = True
    except ImportError:
        validator = None
        use_lib = False

    total = 0
    failed = 0
    for lineno, raw in enumerate(args.ndjson.read_text(encoding="utf-8").splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        total += 1
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[L{lineno}] JSON parse error: {e}", file=sys.stderr)
            failed += 1
            continue
        if use_lib:
            errs = [e.message for e in validator.iter_errors(event)]
        else:
            errs = _validate_manual(event, schema)
        if errs:
            failed += 1
            for e in errs:
                print(f"[L{lineno}] {e}", file=sys.stderr)

    backend = "jsonschema" if use_lib else "manual-fallback"
    print(f"[validate] {total - failed}/{total} OK ({backend})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
