"""Tests for sim-live-telemetry.py — schema conformance and CLI contract."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from conftest import SCRIPTS_DIR, SCHEMAS_DIR

SIM_SCRIPT = SCRIPTS_DIR / "sim-live-telemetry.py"

REQUIRED_FIELDS = {
    "event", "version", "ts_ns", "ts_iso", "host", "metric",
    "tick", "kappa", "cusum_s", "h", "k_slack", "k_short", "k_long",
    "mu_baseline", "switches", "n_pids", "severity", "shadow_mode",
    "alert_cert_path",
}


def _run_sim(tmp_path, duration_sec=2, interval_ms=500):
    out = tmp_path / "alerts.ndjson"
    result = subprocess.run(
        [sys.executable, str(SIM_SCRIPT),
         "--output", str(out),
         "--duration-sec", str(duration_sec),
         "--interval-ms", str(interval_ms)],
        capture_output=True, text=True, timeout=30,
    )
    return result, out


def test_sim_script_exists():
    assert SIM_SCRIPT.is_file(), f"Sim script missing: {SIM_SCRIPT}"


def test_sim_help_flag():
    result = subprocess.run(
        [sys.executable, str(SIM_SCRIPT), "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--duration-sec" in result.stdout
    assert "--interval-ms" in result.stdout


def test_sim_no_rate_flag():
    """--rate must not exist (was documented incorrectly in AGENTS.md)."""
    result = subprocess.run(
        [sys.executable, str(SIM_SCRIPT), "--rate", "2"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, "--rate flag must not be accepted"


def test_sim_produces_ndjson(tmp_path):
    result, out = _run_sim(tmp_path, duration_sec=2, interval_ms=500)
    assert result.returncode == 0, f"Sim exited with error: {result.stderr}"
    assert out.is_file()
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert len(lines) >= 1, "Sim produced no output events"


def test_sim_event_count(tmp_path):
    """2 seconds at 500 ms → 4 events (±1 for rounding)."""
    result, out = _run_sim(tmp_path, duration_sec=2, interval_ms=500)
    assert result.returncode == 0
    lines = [l for l in out.read_text().splitlines() if l.strip()]
    assert 3 <= len(lines) <= 5, f"Expected ~4 events, got {len(lines)}"


def test_sim_events_are_valid_json(tmp_path):
    _, out = _run_sim(tmp_path, duration_sec=1, interval_ms=250)
    for line in out.read_text().splitlines():
        if line.strip():
            event = json.loads(line)
            assert isinstance(event, dict)


def test_sim_events_have_required_fields(tmp_path):
    _, out = _run_sim(tmp_path, duration_sec=1, interval_ms=250)
    for line in out.read_text().splitlines():
        if line.strip():
            event = json.loads(line)
            missing = REQUIRED_FIELDS - set(event.keys())
            assert not missing, f"Event missing fields: {missing}"


def test_sim_event_field_types(tmp_path):
    _, out = _run_sim(tmp_path, duration_sec=1, interval_ms=250)
    for line in out.read_text().splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        assert ev["event"] == "H7_ALERT"
        assert ev["version"] == "1.1"
        assert ev["metric"] == "sched_switch"
        assert isinstance(ev["ts_ns"], int) and ev["ts_ns"] >= 0
        assert isinstance(ev["kappa"], float)
        assert ev["severity"] in ("INFO", "WARN", "CRITICAL")
        assert isinstance(ev["shadow_mode"], bool)
        assert str(ev["alert_cert_path"]).endswith(".cal")


def test_sim_kappa_bounded(tmp_path):
    """kappa must stay in [0.0, 1.0] for all events."""
    _, out = _run_sim(tmp_path, duration_sec=2, interval_ms=250)
    for line in out.read_text().splitlines():
        if line.strip():
            ev = json.loads(line)
            assert 0.0 <= ev["kappa"] <= 1.0, f"kappa out of range: {ev['kappa']}"


def test_sim_tick_monotonically_increases(tmp_path):
    _, out = _run_sim(tmp_path, duration_sec=2, interval_ms=250)
    ticks = [json.loads(l)["tick"] for l in out.read_text().splitlines() if l.strip()]
    for i in range(1, len(ticks)):
        assert ticks[i] > ticks[i - 1], f"tick not monotone at index {i}"


def test_sim_interval_too_small_exits(tmp_path):
    """Intervals < 50 ms should be rejected."""
    result = subprocess.run(
        [sys.executable, str(SIM_SCRIPT),
         "--output", str(tmp_path / "out.ndjson"),
         "--duration-sec", "1",
         "--interval-ms", "10"],
        capture_output=True, text=True,
    )
    assert result.returncode == 2, "Interval < 50 ms should exit with code 2"
