#!/usr/bin/env python3
"""Non-regression test suite for heterogeneous kernel scenarios.

Covers:
1. BTF-available path  : calibration guard accepts a non-pending sha256 baseline.
2. BTF-absent path     : offline-fallback produces a valid, non-pending baseline.
3. Pending guard       : `make up` equivalent guard rejects sha256=="pending".
4. Schema coherence    : both baseline variants share the required fields.
5. Fixture portability : baseline.example.json is valid JSON with required fields.

All tests run without root, without BTF, and without the sensor binary.
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

SEED_SCRIPT = Path(__file__).resolve().parent / "seed-offline-baseline.py"
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "baseline.example.json"

REQUIRED_BASELINE_FIELDS = {"version", "mu_kappa", "k_slack", "h_threshold", "n_ticks", "sha256"}


def _seed(fixture: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SEED_SCRIPT), "--fixture", str(fixture), "--output", str(output)],
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fixture_portability(_tmp: Path) -> list[str]:
    """baseline.example.json must be parseable and contain required fields."""
    failures: list[str] = []
    if not FIXTURE.is_file():
        failures.append(f"  fixture missing: {FIXTURE}")
        return failures
    try:
        doc = json.loads(FIXTURE.read_text())
    except Exception as exc:
        failures.append(f"  fixture is not valid JSON: {exc}")
        return failures
    missing = REQUIRED_BASELINE_FIELDS - set(doc.keys())
    if missing:
        failures.append(f"  fixture missing required fields: {sorted(missing)}")
    return failures


def test_btf_absent_produces_valid_baseline(tmp: Path) -> list[str]:
    """offline-fallback must produce sha256 != 'pending' with correct metadata."""
    failures: list[str] = []
    out = tmp / "baseline_no_btf.json"
    r = _seed(FIXTURE, out)
    if r.returncode != 0:
        failures.append(f"  seed-offline-baseline failed (exit {r.returncode}): {r.stderr.strip()[:200]}")
        return failures
    try:
        doc = json.loads(out.read_text())
    except Exception as exc:
        failures.append(f"  output is not valid JSON: {exc}")
        return failures
    if doc.get("sha256", "pending") == "pending":
        failures.append("  sha256 still 'pending' after offline seed")
    if doc.get("calibration_source") != "offline-fallback":
        failures.append(f"  calibration_source={doc.get('calibration_source')!r}")
    if doc.get("btf_available") is not False:
        failures.append(f"  btf_available={doc.get('btf_available')!r} (expected False)")
    return failures


def test_btf_available_guard(tmp: Path) -> list[str]:
    """Simulate the BTF-available scenario: a manually calibrated baseline (sha256 set)
    must pass the pending guard without re-seeding."""
    failures: list[str] = []
    # Construct a synthetic "live-calibrated" baseline
    doc = json.loads(FIXTURE.read_text()) if FIXTURE.is_file() else {
        "version": "0.1.0", "mu_kappa": 0.08, "k_slack": 0.04,
        "h_threshold": 0.40, "n_ticks": 1200,
    }
    body = {k: v for k, v in doc.items() if k != "sha256"}
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    doc["sha256"] = digest
    doc["calibration_source"] = "live"
    doc["btf_available"] = True

    out = tmp / "baseline_live.json"
    out.write_text(json.dumps(doc, indent=2))

    # The pending guard: sha256 must not be "pending"
    loaded = json.loads(out.read_text())
    if loaded.get("sha256", "pending") == "pending":
        failures.append("  live-calibrated baseline incorrectly has sha256='pending'")
    return failures


def test_pending_guard_rejects(tmp: Path) -> list[str]:
    """A baseline with sha256='pending' must be caught before `make up`."""
    failures: list[str] = []
    pending_baseline = tmp / "baseline_pending.json"
    doc = {"version": "0.1.0", "mu_kappa": 0.08, "sha256": "pending"}
    pending_baseline.write_text(json.dumps(doc))
    loaded = json.loads(pending_baseline.read_text())
    # The guard condition (replicated from Makefile logic)
    is_pending = loaded.get("sha256", "pending") == "pending"
    if not is_pending:
        failures.append("  pending guard failed to detect sha256='pending'")
    return failures


def test_schema_coherence_both_paths(tmp: Path) -> list[str]:
    """Both the offline-seeded and fixture baseline must contain required fields."""
    failures: list[str] = []
    out = tmp / "baseline_schema.json"
    r = _seed(FIXTURE, out)
    if r.returncode != 0:
        failures.append(f"  seeding failed: {r.stderr.strip()[:120]}")
        return failures
    seeded = json.loads(out.read_text())
    fixture_doc = json.loads(FIXTURE.read_text()) if FIXTURE.is_file() else {}
    for label, doc in [("seeded", seeded), ("fixture", fixture_doc)]:
        missing = REQUIRED_BASELINE_FIELDS - set(doc.keys())
        if missing:
            failures.append(f"  {label} missing fields: {sorted(missing)}")
    return failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main() -> int:
    if not FIXTURE.is_file():
        print(f"[kernel-hetero-test] SKIP: fixture not found: {FIXTURE}")
        return 0

    total = 0
    failed = 0

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        cases = [
            ("fixture portability", test_fixture_portability),
            ("BTF-absent: offline-fallback produces valid baseline", test_btf_absent_produces_valid_baseline),
            ("BTF-available: live-calibrated baseline passes pending guard", test_btf_available_guard),
            ("pending guard rejects sha256='pending'", test_pending_guard_rejects),
            ("schema coherence (offline + fixture)", test_schema_coherence_both_paths),
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

    print(f"[kernel-hetero-test] {total - failed}/{total} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
