"""Tests for seed-offline-baseline.py — canonical hash and CLI contract."""

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from conftest import FIXTURES_DIR, SCRIPTS_DIR, REPO_ROOT

SEED_SCRIPT = SCRIPTS_DIR / "seed-offline-baseline.py"


def _import_seed():
    spec = importlib.util.spec_from_file_location("seed_offline_baseline", SEED_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_script_exists():
    assert SEED_SCRIPT.is_file(), f"Seed script missing: {SEED_SCRIPT}"


def test_canonical_bytes_excludes_sha256_key():
    mod = _import_seed()
    doc = {"mu_kappa": 0.08, "sha256": "some-hash", "h_threshold": 0.4}
    canon = mod._canonical_bytes(doc)
    parsed = json.loads(canon.decode())
    assert "sha256" not in parsed
    assert "mu_kappa" in parsed
    assert "h_threshold" in parsed


def test_canonical_bytes_is_sorted():
    mod = _import_seed()
    doc = {"z_field": 1, "a_field": 2}
    canon = mod._canonical_bytes(doc)
    assert canon == b'{"a_field":2,"z_field":1}'


def test_canonical_bytes_no_whitespace():
    mod = _import_seed()
    doc = {"key": "value"}
    canon = mod._canonical_bytes(doc)
    assert b" " not in canon


def test_seed_produces_valid_sha256(tmp_path):
    """End-to-end: seeding the fixture produces a verifiable sha256.

    The seed script hashes the fixture body (minus sha256) BEFORE appending
    calibration_source / btf_available.  Verification must reproduce that
    same pre-append state from the fixture, not from the output doc.
    """
    output = tmp_path / "baseline.json"
    fixture = FIXTURES_DIR / "baseline.example.json"
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT),
         "--fixture", str(fixture),
         "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Seed failed: {result.stderr}"
    assert output.is_file()
    out_doc = json.loads(output.read_text())

    assert out_doc.get("sha256") not in (None, "pending"), "sha256 must be filled after seeding"

    # Reconstruct what the seeder hashed: fixture body minus sha256 key.
    fixture_doc = json.loads(fixture.read_text())
    mod = _import_seed()
    expected = hashlib.sha256(mod._canonical_bytes(fixture_doc)).hexdigest()
    assert out_doc["sha256"] == expected, (
        "sha256 must equal the canonical hash of the fixture body (sha256 key excluded)"
    )


def test_seed_adds_calibration_metadata(tmp_path):
    output = tmp_path / "baseline.json"
    fixture = FIXTURES_DIR / "baseline.example.json"
    subprocess.run([sys.executable, str(SEED_SCRIPT),
                    "--fixture", str(fixture), "--output", str(output)],
                   check=True, capture_output=True)
    doc = json.loads(output.read_text())
    assert doc.get("calibration_source") == "offline-fallback"
    assert doc.get("btf_available") is False


def test_seed_missing_fixture_exits_2(tmp_path):
    output = tmp_path / "baseline.json"
    result = subprocess.run(
        [sys.executable, str(SEED_SCRIPT),
         "--fixture", str(tmp_path / "nonexistent.json"),
         "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2


def test_seed_idempotent(tmp_path):
    """Seeding twice produces byte-identical output (deterministic)."""
    output1 = tmp_path / "b1.json"
    output2 = tmp_path / "b2.json"
    fixture = FIXTURES_DIR / "baseline.example.json"
    cmd = [sys.executable, str(SEED_SCRIPT), "--fixture", str(fixture)]
    subprocess.run(cmd + ["--output", str(output1)], check=True, capture_output=True)
    subprocess.run(cmd + ["--output", str(output2)], check=True, capture_output=True)
    assert output1.read_text() == output2.read_text()
