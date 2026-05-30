#!/usr/bin/env python3
"""Generate a signed non-drift report from the NDJSON alert feed.

Reads alerts.ndjson, computes κ statistics per agent and globally,
then produces a JSON report signed with the local Ed25519 cert-issuer key.

The report is "non-drift" when:
  - kappa_max < h_threshold (no BREACH event in the window)
  - kappa_mean < mu_baseline + 2*k_slack (stable baseline)

Output:
  run/reports/drift-report-YYYY-MM-DDTHH-MM-SSZ.json
  run/reports/drift-report-YYYY-MM-DDTHH-MM-SSZ.json.sig  (raw Ed25519 sig hex)

Usage:
  python3 scripts/gen-drift-report.py \\
      --alerts-ndjson run/logs/alerts.ndjson \\
      --baseline      run/baseline.json \\
      --keys-dir      run/keys \\
      --since-hours   24
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption, load_pem_private_key,
    )
except ImportError:
    raise SystemExit("Missing dependency: pip install cryptography")

_ISSUER_PEM = "h7-cert-issuer.sec"
_ISSUER_PUB = "h7-cert-issuer.pub"
REPORT_SCHEMA = "h7-drift-report/v1"


def _load_key(keys_dir: Path) -> tuple[Ed25519PrivateKey, bytes]:
    priv_path = keys_dir / _ISSUER_PEM
    if not priv_path.is_file():
        raise SystemExit(f"[gen-drift-report] cert-issuer key not found: {priv_path}\nRun 'make setup' first.")
    with open(priv_path, "rb") as f:
        priv = load_pem_private_key(f.read(), password=None)
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv, pub


def _pub_fingerprint(pub: bytes) -> str:
    import hashlib
    return "h7-cert-issuer-" + hashlib.sha256(pub).hexdigest()[:16]


def _canonical(body: dict) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load_alerts(path: Path, since_ns: int) -> list[dict]:
    alerts = []
    if not path.is_file():
        return alerts
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                a = json.loads(line)
                if int(a.get("ts_ns", 0)) >= since_ns:
                    alerts.append(a)
            except (json.JSONDecodeError, ValueError):
                continue
    return alerts


def _load_baseline(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _entity_id(a: dict) -> str:
    return a.get("agent_id") or a.get("host", "unknown")


def _agent_stats(alerts: list[dict], h_default: float) -> list[dict]:
    from collections import defaultdict
    by_entity: dict[str, list[dict]] = defaultdict(list)
    for a in alerts:
        by_entity[_entity_id(a)].append(a)

    stats = []
    for eid, events in by_entity.items():
        kappas = [float(e["kappa"]) for e in events if "kappa" in e]
        cusums = [float(e.get("cusum_s", 0)) for e in events]
        h_vals = [float(e.get("h", h_default)) for e in events]
        h_val = h_vals[-1] if h_vals else h_default

        breaches = sum(1 for k in kappas if k >= h_val)
        kappa_max = max(kappas) if kappas else 0.0
        kappa_mean = sum(kappas) / len(kappas) if kappas else 0.0
        cusum_max = max(cusums) if cusums else 0.0

        # Non-drift verdict: no BREACH and mean stable
        verdict = "NOMINAL" if (breaches == 0 and kappa_max < h_val) else "DRIFT_DETECTED"

        stats.append({
            "entity_id": eid,
            "alert_count": len(events),
            "kappa_min": round(min(kappas), 6) if kappas else None,
            "kappa_max": round(kappa_max, 6),
            "kappa_mean": round(kappa_mean, 6),
            "cusum_max": round(cusum_max, 6),
            "h_threshold": round(h_val, 6),
            "breach_count": breaches,
            "verdict": verdict,
        })

    stats.sort(key=lambda s: (s["verdict"] != "DRIFT_DETECTED", -s["kappa_max"]))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--alerts-ndjson", type=Path, default=Path("run/logs/alerts.ndjson"))
    parser.add_argument("--baseline", type=Path, default=Path("run/baseline.json"))
    parser.add_argument("--keys-dir", type=Path, default=Path("run/keys"))
    parser.add_argument("--output-dir", type=Path, default=Path("run/reports"))
    parser.add_argument("--since-hours", type=float, default=24.0,
                        help="Window of alerts to analyse (default: 24h)")
    args = parser.parse_args()

    priv, pub = _load_key(args.keys_dir)
    baseline = _load_baseline(args.baseline)

    now = datetime.now(timezone.utc)
    since_ns = int((now - timedelta(hours=args.since_hours)).timestamp() * 1_000_000_000)
    alerts = _load_alerts(args.alerts_ndjson, since_ns)

    h_default = float(baseline.get("h_threshold", 0.40))
    mu_baseline = float(baseline.get("mu_kappa", 0.08))

    agent_stats = _agent_stats(alerts, h_default)
    global_kappas = [float(a["kappa"]) for a in alerts if "kappa" in a]
    total_breaches = sum(s["breach_count"] for s in agent_stats)

    global_verdict = "NOMINAL" if total_breaches == 0 else "DRIFT_DETECTED"

    body = {
        "schema": REPORT_SCHEMA,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_hours": args.since_hours,
        "since": datetime.fromtimestamp(since_ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issuer_key_fingerprint": _pub_fingerprint(pub),
        "baseline_sha256": baseline.get("sha256", ""),
        "baseline_source": baseline.get("calibration_source", "live"),
        "global_verdict": global_verdict,
        "total_alerts": len(alerts),
        "total_breach_events": total_breaches,
        "global_kappa_mean": round(sum(global_kappas) / len(global_kappas), 6) if global_kappas else None,
        "global_kappa_max": round(max(global_kappas), 6) if global_kappas else None,
        "h_threshold": h_default,
        "mu_baseline": mu_baseline,
        "agents": agent_stats,
    }

    sig = priv.sign(_canonical(body))
    sig_b64 = base64.b64encode(sig).decode()

    report = {"body": body, "sig_b64": sig_b64}

    stamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"drift-report-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    drift_agents = [s for s in agent_stats if s["verdict"] == "DRIFT_DETECTED"]
    print(f"[gen-drift-report] {out_path}")
    print(f"  window       : {args.since_hours}h")
    print(f"  alerts       : {len(alerts)}")
    print(f"  agents       : {len(agent_stats)}")
    print(f"  drift agents : {len(drift_agents)}")
    print(f"  verdict      : {global_verdict}")
    print(f"  signed by    : {_pub_fingerprint(pub)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
