"""Shared fixtures for h7-demo-kit test suite."""

from pathlib import Path
import pytest

REPO_ROOT   = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
FIXTURES_DIR = REPO_ROOT / "fixtures"
DOCS_DIR    = REPO_ROOT / "docs"
SCHEMAS_DIR = DOCS_DIR / "schemas"
