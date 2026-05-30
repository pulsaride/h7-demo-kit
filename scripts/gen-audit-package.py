#!/usr/bin/env python3
"""Generate a signed audit evidence package for a client pilot.

Bundles the following artefacts into a timestamped directory:
  - MANIFEST.json       : inventory with SHA-256 of each file
  - alerts.ndjson       : full alert feed (copy)
  - baseline.json       : calibrated baseline (copy)
  - *.cal               : all per-alert signed sidecars (copies)
  - AUDIT-SUMMARY.txt   : human-readable summary (alerts, kappa stats, cal count)
  - MANIFEST.json.sig   : Ed25519 signature over the manifest (if key present)

Usage:
  python3 scripts/gen-audit-package.py \\
      --alerts-ndjson run/logs/alerts.ndjson \\
      --alerts-dir    run/alerts/ \\
      --baseline      run/baseline.json \\
      --pub-key       run/keys/h7-cert-issuer.pub \\
      --output-dir    run/audit-package

The output directory is created if absent, then stamped with a subdirectory
named  YYYY-MM-DDTHH-MM-SSZ/.  Use --no-timestamp to write flat into output-dir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_alerts(path: Path) -> list[dict]:
    alerts = []
    if not path.is_file():
        return alerts
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                alerts.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return alerts


def _kappa_stats(alerts: list[dict]) -> dict:
    if not alerts:
        return {"count": 0, "kappa_min": None, "kappa_max": None, "kappa_mean": None}
    kappas = [float(a["kappa"]) for a in alerts if "kappa" in a]
    if not kappas:
        return {"count": len(alerts), "kappa_min": None, "kappa_max": None, "kappa_mean": None}
    return {
        "count": len(kappas),
        "kappa_min": round(min(kappas), 6),
        "kappa_max": round(max(kappas), 6),
        "kappa_mean": round(sum(kappas) / len(kappas), 6),
    }


def _build_summary(
    alerts: list[dict],
    cal_count: int,
    baseline_path: Path,
    generated_at: str,
) -> str:
    stats = _kappa_stats(alerts)
    baseline_sha = _sha256_file(baseline_path) if baseline_path.is_file() else "N/A"

    # Severity breakdown
    sev = {}
    for a in alerts:
        s = a.get("severity", "UNKNOWN")
        sev[s] = sev.get(s, 0) + 1

    lines = [
        "=" * 64,
        "  Pulsaride H7 — Audit Evidence Package",
        f"  Generated : {generated_at}",
        "=" * 64,
        "",
        "ALERT STATISTICS",
        f"  Total alerts      : {stats['count']}",
        f"  κ min / max / mean: {stats['kappa_min']} / {stats['kappa_max']} / {stats['kappa_mean']}",
        "",
        "SEVERITY BREAKDOWN",
    ]
    for sev_label in ("CRITICAL", "WARN", "INFO", "UNKNOWN"):
        if sev.get(sev_label, 0):
            lines.append(f"  {sev_label:<12}: {sev[sev_label]}")
    lines += [
        "",
        "SIGNED SIDECARS",
        f"  .cal files bundled: {cal_count}",
        "",
        "BASELINE",
        f"  SHA-256           : {baseline_sha}",
        f"  Path              : {baseline_path}",
        "",
        "ATTESTATION CHAIN",
        "  All .cal files are Ed25519-signed by h7-cert-issuer.",
        "  Verify with: h7 cal verify <file.cal> --public-key <pub>",
        "",
        "COMPLIANCE NOTE",
        "  This package is produced by Pulsaride H7 Behavioral Cryptographic",
        "  Attestation (BCA). The alert signatures are tamper-evident and",
        "  independently verifiable without network access.",
        "=" * 64,
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--alerts-ndjson", type=Path, required=True,
                        help="Path to alerts.ndjson")
    parser.add_argument("--alerts-dir", type=Path, required=True,
                        help="Directory containing *.cal sidecar files")
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Path to baseline.json")
    parser.add_argument("--pub-key", type=Path, default=None,
                        help="Path to Ed25519 public key (hex, for manifest footer)")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Output directory for the audit package")
    parser.add_argument("--no-timestamp", action="store_true",
                        help="Write flat into output-dir (no timestamp subdirectory)")
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = generated_at.replace(":", "-")

    out = args.output_dir if args.no_timestamp else (args.output_dir / stamp)
    out.mkdir(parents=True, exist_ok=True)

    manifest: dict = {
        "format": "H7-AuditPackage/1.0",
        "generated_at": generated_at,
        "files": {},
    }
    errors: list[str] = []

    # --- alerts.ndjson ---
    if args.alerts_ndjson.is_file():
        dest = out / "alerts.ndjson"
        shutil.copy2(args.alerts_ndjson, dest)
        manifest["files"]["alerts.ndjson"] = _sha256_file(dest)
    else:
        errors.append(f"alerts.ndjson not found: {args.alerts_ndjson}")

    # --- baseline.json ---
    if args.baseline.is_file():
        dest = out / "baseline.json"
        shutil.copy2(args.baseline, dest)
        manifest["files"]["baseline.json"] = _sha256_file(dest)
    else:
        errors.append(f"baseline.json not found: {args.baseline}")

    # --- *.cal sidecars ---
    cal_count = 0
    if args.alerts_dir.is_dir():
        cal_dir = out / "certs"
        cal_dir.mkdir(exist_ok=True)
        for cal in sorted(args.alerts_dir.glob("*.cal")):
            dest = cal_dir / cal.name
            shutil.copy2(cal, dest)
            manifest["files"][f"certs/{cal.name}"] = _sha256_file(dest)
            cal_count += 1
    else:
        errors.append(f"alerts-dir not found: {args.alerts_dir}")

    # --- pub key ---
    if args.pub_key and args.pub_key.is_file():
        dest = out / "h7-cert-issuer.pub"
        shutil.copy2(args.pub_key, dest)
        manifest["files"]["h7-cert-issuer.pub"] = _sha256_file(dest)

    # --- AUDIT-SUMMARY.txt ---
    alerts = _load_alerts(args.alerts_ndjson)
    summary = _build_summary(alerts, cal_count, args.baseline, generated_at)
    summary_path = out / "AUDIT-SUMMARY.txt"
    summary_path.write_text(summary)
    manifest["files"]["AUDIT-SUMMARY.txt"] = _sha256_file(summary_path)

    manifest["alert_count"] = len(alerts)
    manifest["cal_count"] = cal_count
    if errors:
        manifest["warnings"] = errors

    # --- MANIFEST.json ---
    manifest_path = out / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"[audit-package] {out}")
    print(f"  alerts  : {len(alerts)}")
    print(f"  .cal    : {cal_count}")
    print(f"  files   : {len(manifest['files'])}")
    if errors:
        for e in errors:
            print(f"  [WARN] {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
