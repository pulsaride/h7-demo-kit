#!/usr/bin/env python3
"""Deterministic live telemetry simulator for h7-monitor UI testing.

Appends one NDJSON event every 500 ms (configurable) to run/logs/alerts.ndjson,
following the frozen H7_ALERT v1.1 schema.

Signal profile repeats in 60-second cycles:
- Phase A (0-30s): nominal kappa in [0.01, 0.04]
- Phase B (30-45s): breach ramp peaking in [0.65, 0.85]
- Phase C (45-60s): recovery to nominal baseline
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def _phase_kappa(t_cycle: float) -> float:
    # Phase A: smooth nominal oscillation constrained to [0.01, 0.04].
    if t_cycle < 30.0:
        k = 0.025 + 0.015 * math.sin(2.0 * math.pi * (t_cycle / 10.0))
        return max(0.01, min(0.04, k))

    # Phase B: deterministic anomaly breach, peaking around 0.8.
    if t_cycle < 45.0:
        x = (t_cycle - 30.0) / 15.0  # 0..1
        # Smoothstep for deterministic ramp shape.
        s = x * x * (3.0 - 2.0 * x)
        # Peak in [0.65, 0.85] with slight deterministic ripple.
        return 0.08 + 0.72 * s + 0.04 * math.sin(2.0 * math.pi * x)

    # Phase C: exponential-like decay from breach back to nominal baseline.
    x = (t_cycle - 45.0) / 15.0  # 0..1
    recovery = 0.70 * math.exp(-3.2 * x)
    baseline = 0.024 + 0.006 * math.sin(2.0 * math.pi * x)
    return max(0.01, min(0.85, baseline + recovery))


def _severity(kappa: float, h: float) -> str:
    if kappa >= h:
        return "CRITICAL"
    if kappa >= (0.5 * h):
        return "WARN"
    return "INFO"


def _build_event(
    *,
    tick: int,
    elapsed_ns: int,
    kappa: float,
    cusum_s: float,
    h: float,
    k_slack: float,
    k_short: int,
    k_long: int,
    mu_baseline: float,
    host: str,
    alert_dir: Path,
) -> dict:
    switches = int(1200 + (kappa * 42000.0))
    n_pids = int(8 + (kappa * 90.0))
    cert_name = f"alert-{tick:06d}.cal"
    cert_path = alert_dir / cert_name

    return {
        "event": "H7_ALERT",
        "version": "1.1",
        "ts_ns": elapsed_ns,
        "ts_iso": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "host": host,
        "metric": "sched_switch",
        "tick": tick,
        "kappa": round(kappa, 6),
        "cusum_s": round(cusum_s, 6),
        "h": h,
        "k_slack": k_slack,
        "k_short": k_short,
        "k_long": k_long,
        "mu_baseline": mu_baseline,
        "switches": switches,
        "n_pids": n_pids,
        "severity": _severity(kappa, h),
        "shadow_mode": False,
        "alert_cert_path": str(cert_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Append deterministic mock H7 telemetry to alerts.ndjson")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("run/logs/alerts.ndjson"),
        help="NDJSON output path (default: run/logs/alerts.ndjson)",
    )
    parser.add_argument(
        "--interval-ms",
        type=int,
        default=500,
        help="Emit interval in milliseconds (default: 500)",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=0.0,
        help="Optional total duration in seconds; 0 means run until interrupted",
    )
    args = parser.parse_args()

    if args.interval_ms < 50:
        print("[sim] interval too small; use >= 50 ms", file=sys.stderr)
        return 2

    out_path = args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    alert_dir = out_path.parent.parent / "alerts"
    alert_dir.mkdir(parents=True, exist_ok=True)

    host = socket.gethostname()
    h = 0.32
    k_slack = 0.02
    k_short = 5
    k_long = 30
    mu_baseline = 0.024

    interval_s = args.interval_ms / 1000.0
    start_mono = time.monotonic()
    tick = 0
    cusum_s = 0.0

    print(f"[sim] writing to {out_path}")
    print("[sim] phases: A(0-30s) nominal, B(30-45s) breach, C(45-60s) recovery")
    print("[sim] press Ctrl+C to stop")

    with out_path.open("a", encoding="utf-8") as f:
        try:
            while True:
                now = time.monotonic()
                elapsed_s = now - start_mono
                if args.duration_sec > 0.0 and elapsed_s >= args.duration_sec:
                    break

                t_cycle = elapsed_s % 60.0
                kappa = _phase_kappa(t_cycle)

                # One-sided CUSUM style accumulator around baseline+slack.
                cusum_s = max(0.0, cusum_s + (kappa - (mu_baseline + k_slack)))

                event = _build_event(
                    tick=tick,
                    elapsed_ns=time.time_ns(),
                    kappa=kappa,
                    cusum_s=cusum_s,
                    h=h,
                    k_slack=k_slack,
                    k_short=k_short,
                    k_long=k_long,
                    mu_baseline=mu_baseline,
                    host=host,
                    alert_dir=alert_dir,
                )

                f.write(json.dumps(event, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())

                tick += 1
                time.sleep(interval_s)
        except KeyboardInterrupt:
            print("\n[sim] stopped by user")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
