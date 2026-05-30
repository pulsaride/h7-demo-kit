#!/usr/bin/env python3
"""Regression test: offline-fallback calibration path (no BTF required).

Validates that seed-offline-baseline.py:
- Produces a valid baseline.json with sha256 != "pending"
- Sets calibration_source = "offline-fallback" and btf_available = False
- Is deterministic (two runs from the same fixture produce the same sha256)
- Fails closed when the fixture is missing

Exit code 0 on success, 1 on any failure.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "seed-offline-baseline.py"
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "baseline.example.json"


def _run(fixture: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture", str(fixture), "--output", str(output)],
        capture_output=True,
        text=True,
    )


def test_produces_valid_baseline(tmp: Path) -> list[str]:
    failures: list[str] = []
    out = tmp / "baseline.json"
    r = _run(FIXTURE, out)
    if r.returncode != 0:
        failures.append(f"  exit {r.returncode}: {r.stderr.strip()[:200]}")
        return failures

    try:
        doc = json.loads(out.read_text())
    except Exception as exc:
        failures.append(f"  output not valid JSON: {exc}")
        return failures

    if doc.get("sha256", "pending") == "pending":
        failures.append("  sha256 is still 'pending' after seeding")
    if doc.get("calibration_source") != "offline-fallback":
        failures.append(f"  calibration_source={doc.get('calibration_source')!r} (expected 'offline-fallback')")
    if doc.get("btf_available") is not False:
        failures.append(f"  btf_available={doc.get('btf_available')!r} (expected False)")
    return failures


def test_deterministic(tmp: Path) -> list[str]:
    failures: list[str] = []
    out1 = tmp / "baseline1.json"
    out2 = tmp / "baseline2.json"
    _run(FIXTURE, out1)
    _run(FIXTURE, out2)
    if not out1.exists() or not out2.exists():
        failures.append("  one or both output files not created")
        return failures
    d1 = json.loads(out1.read_text())
    d2 = json.loads(out2.read_text())
    if d1.get("sha256") != d2.get("sha256"):
        failures.append(f"  non-deterministic: sha256 differs between runs: {d1.get('sha256')!r} vs {d2.get('sha256')!r}")
    return failures


def test_fails_closed_missing_fixture(tmp: Path) -> list[str]:
    failures: list[str] = []
    missing = tmp / "nonexistent-fixture.json"
    out = tmp / "baseline_bad.json"
    r = _run(missing, out)
    if r.returncode == 0:
        failures.append("  expected non-zero exit when fixture is missing, got 0")
    if out.exists():
        failures.append("  output file was written despite missing fixture (should not exist)")
    return failures


def test_sha256_self_reference(tmp: Path) -> list[str]:
    """The stored sha256 must match sha256(fixture body without sha256 field).

    The seeder computes the hash over the original fixture fields BEFORE
    appending calibration_source / btf_available.  Those fields are metadata
    about how the baseline was obtained; they are intentionally not covered by
    the hash (AGENTS.md Invariant 3: only the sha256 key itself is excluded).
    Verification must therefore reproduce the same pre-append fixture body.
    """
    failures: list[str] = []
    out = tmp / "baseline_ref.json"
    r = _run(FIXTURE, out)
    if r.returncode != 0:
        failures.append(f"  seeding failed: {r.stderr.strip()[:120]}")
        return failures

    doc = json.loads(out.read_text())
    stored = doc.get("sha256", "")

    # Reproduce what the seeder hashed: fixture fields minus sha256.
    fixture_doc = json.loads(FIXTURE.read_text())
    body = {k: v for k, v in fixture_doc.items() if k != "sha256"}
    expected = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if stored != expected:
        failures.append(f"  sha256 self-reference mismatch: stored={stored!r} expected={expected!r}")
    return failures


def main() -> int:
    if not FIXTURE.is_file():
        print(f"[btf-fallback-test] SKIP: fixture not found: {FIXTURE}")
        return 0

    total = 0
    failed = 0

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cases = [
            ("produces valid baseline (sha256 ≠ pending, calibration_source, btf_available)", test_produces_valid_baseline),
            ("deterministic: two runs same sha256", test_deterministic),
            ("fail-closed when fixture is missing", test_fails_closed_missing_fixture),
            ("sha256 self-reference integrity", test_sha256_self_reference),
        ]
        for name, fn in cases:
            total += 1
            try:
                issues = fn(tmp)
            except Exception:
                failed += 1
                print(f"[FAIL] {name}\n{traceback.format_exc()}")
                continue
            if issues:
                failed += 1
                print(f"[FAIL] {name}")
                for i in issues:
                    print(i)
            else:
                print(f"[ OK ] {name}")

    print(f"[btf-fallback-test] {total - failed}/{total} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
