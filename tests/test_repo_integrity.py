"""Repo-level integrity checks — mandatory files, no broken cross-repo refs."""

from pathlib import Path

from conftest import REPO_ROOT, SCRIPTS_DIR, FIXTURES_DIR

MANDATORY_SCRIPTS = [
    "sim-live-telemetry.py",
    "seed-offline-baseline.py",
    "verify-gate-hardening.py",
    "attack-noise.py",
    "demo-sinkhole.py",
    "gen-audit-package.py",
    "gen-crl.py",
    "validate-crl.py",
    "validate-alerts-ndjson.py",
    "test-btf-fallback.py",
    "test-kernel-heterogeneous.py",
]

MANDATORY_ROOT_FILES = [
    "AGENTS.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "THREAT-MODEL.md",
    "LICENSE",
    "Makefile",
    "README.md",
]

MANDATORY_DOCS = [
    "docs/schemas/alert-v1.1.json",
    "docs/EU-AI-ACT-TRACEABILITY.md",
    "docs/PUBLIC-READINESS.md",
]

MANDATORY_FIXTURES = [
    "fixtures/baseline.example.json",
    "fixtures/H7_RELEASE_SIGNING.pub",
    "fixtures/README.md",
]


def test_mandatory_scripts_present():
    for name in MANDATORY_SCRIPTS:
        path = SCRIPTS_DIR / name
        assert path.is_file(), f"Mandatory script missing: scripts/{name}"


def test_mandatory_root_files_present():
    for name in MANDATORY_ROOT_FILES:
        path = REPO_ROOT / name
        assert path.is_file(), f"Mandatory root file missing: {name}"


def test_mandatory_docs_present():
    for rel in MANDATORY_DOCS:
        path = REPO_ROOT / rel
        assert path.is_file(), f"Mandatory doc missing: {rel}"


def test_mandatory_fixtures_present():
    for rel in MANDATORY_FIXTURES:
        path = REPO_ROOT / rel
        assert path.is_file(), f"Mandatory fixture missing: {rel}"


def test_no_cross_repo_paths_in_security_md():
    content = (REPO_ROOT / "SECURITY.md").read_text()
    assert "../PulsarideShield" not in content
    assert "PulsarideShield" not in content


def test_agents_md_no_invented_flags():
    content = (REPO_ROOT / "AGENTS.md").read_text()
    assert " --rate " not in content, "AGENTS.md must not mention --rate (flag does not exist)"
    assert "--duration-sec" in content


def test_signing_pub_key_is_pem_or_raw():
    pub = FIXTURES_DIR / "H7_RELEASE_SIGNING.pub"
    content = pub.read_bytes()
    assert len(content) > 0, "H7_RELEASE_SIGNING.pub is empty"


def test_schema_file_has_no_trailing_changes():
    """Frozen schema: must not contain draft marker or TODO comments."""
    schema_text = (REPO_ROOT / "docs" / "schemas" / "alert-v1.1.json").read_text()
    assert "TODO" not in schema_text
    assert "FIXME" not in schema_text


def test_makefile_phony_includes_test():
    makefile = (REPO_ROOT / "Makefile").read_text()
    assert "test" in makefile, "Makefile must have a 'test' target"
