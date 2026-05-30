"""Tests for frozen AlertCert v1.1 schema and fixture integrity."""

import json
import re
from pathlib import Path

from conftest import FIXTURES_DIR, SCHEMAS_DIR, REPO_ROOT


REQUIRED_ALERT_FIELDS = {
    "event", "version", "ts_ns", "ts_iso", "host", "metric",
    "tick", "kappa", "cusum_s", "h", "k_slack", "k_short", "k_long",
    "mu_baseline", "switches", "n_pids", "severity", "shadow_mode",
    "alert_cert_path",
}


def test_alert_schema_is_valid_json():
    schema_path = SCHEMAS_DIR / "alert-v1.1.json"
    assert schema_path.is_file(), f"Schema missing: {schema_path}"
    schema = json.loads(schema_path.read_text())
    assert schema["title"] == "H7_ALERT v1.1"
    assert schema["type"] == "object"


def test_alert_schema_required_fields_complete():
    schema = json.loads((SCHEMAS_DIR / "alert-v1.1.json").read_text())
    assert set(schema["required"]) == REQUIRED_ALERT_FIELDS


def test_alert_schema_additionalproperties_false():
    schema = json.loads((SCHEMAS_DIR / "alert-v1.1.json").read_text())
    assert schema.get("additionalProperties") is False, (
        "Alert schema must forbid extra fields (additionalProperties: false)"
    )


def test_alert_schema_event_const():
    schema = json.loads((SCHEMAS_DIR / "alert-v1.1.json").read_text())
    assert schema["properties"]["event"]["const"] == "H7_ALERT"


def test_alert_schema_version_const():
    schema = json.loads((SCHEMAS_DIR / "alert-v1.1.json").read_text())
    assert schema["properties"]["version"]["const"] == "1.1"


def test_baseline_fixture_is_valid_json():
    fixture = FIXTURES_DIR / "baseline.example.json"
    assert fixture.is_file(), f"Fixture missing: {fixture}"
    doc = json.loads(fixture.read_text())
    assert isinstance(doc, dict)


def test_baseline_fixture_has_required_fields():
    doc = json.loads((FIXTURES_DIR / "baseline.example.json").read_text())
    for field in ("version", "mu_kappa", "h_threshold"):
        assert field in doc, f"Baseline fixture missing field: {field}"


def test_baseline_fixture_sha256_is_pending():
    """The pinned fixture ships with sha256=pending; seed-offline-baseline.py fills it."""
    doc = json.loads((FIXTURES_DIR / "baseline.example.json").read_text())
    assert doc.get("sha256") == "pending", (
        "fixtures/baseline.example.json must ship with sha256=pending "
        "(seed-offline-baseline.py computes it at runtime)"
    )


def test_threat_model_exists():
    tm = REPO_ROOT / "THREAT-MODEL.md"
    assert tm.is_file(), "THREAT-MODEL.md missing — referenced from SECURITY.md"


def test_security_md_link_is_local():
    """SECURITY.md must not reference cross-repo paths outside h7-demo-kit."""
    security = REPO_ROOT / "SECURITY.md"
    content = security.read_text()
    assert "PulsarideShield" not in content, (
        "SECURITY.md contains a cross-repo path (../PulsarideShield/...) — "
        "replace with an in-repo path"
    )


def test_agents_md_correct_gate_count():
    agents = REPO_ROOT / "AGENTS.md"
    content = agents.read_text()
    assert "3/3 OK requis" in content, "AGENTS.md must say '3/3 OK requis' (not 2/2)"


def test_agents_md_correct_cli_flags():
    agents = REPO_ROOT / "AGENTS.md"
    content = agents.read_text()
    assert "--duration-sec" in content, "AGENTS.md must use --duration-sec (not --duration)"
    assert "--interval-ms" in content, "AGENTS.md must use --interval-ms (not --rate)"
    assert "--rate" not in content, "AGENTS.md must not reference the non-existent --rate flag"
