#!/usr/bin/env python3
"""Request RFC 3161 timestamps from FreeTSA (and optionally DigiCert) for .cal files.

Design from ADR-PROD-009. The sensor never contacts TSAs — this batch script
runs separately on a machine with network access and produces .tsr sidecar
files alongside the .cal files.

Requires: openssl (system), requests (pip install requests)

Usage:
  # Timestamp a single .cal file
  python3 scripts/ts-request.py --file run/alerts/alert-000001.cal

  # Harvest all .cal files modified in the last hour
  python3 scripts/ts-request.py --harvest run/alerts/ --since-minutes 60

  # Verify an existing TSR sidecar
  python3 scripts/ts-request.py --verify run/alerts/alert-000001.cal \\
      --tsr run/alerts/alert-000001.cal.tsr.freetsa

Output sidecars:
  <file>.tsr.freetsa   — TimeStampToken DER from FreeTSA
  <file>.tsr.digicert  — TimeStampToken DER from DigiCert (if --digicert)
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# TSA endpoints (ADR-PROD-009 §3.4)
TSA_FREETSA = "https://freetsa.org/tsr"
TSA_DIGICERT = "https://timestamp.digicert.com"


def _sha256_file(path: Path) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.digest()


def _openssl_available() -> bool:
    try:
        r = subprocess.run(["openssl", "version"], capture_output=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _ts_request(file_path: Path, tsa_url: str, tsa_name: str, timeout: int = 30) -> Path | None:
    """Request a TSR from the given TSA for file_path. Returns sidecar path or None on error."""
    try:
        import requests
    except ImportError:
        print("[ts-request] ERROR: 'requests' not installed. pip install requests", file=sys.stderr)
        return None

    if not _openssl_available():
        print("[ts-request] ERROR: 'openssl' not found in PATH", file=sys.stderr)
        return None

    sidecar = file_path.parent / f"{file_path.name}.tsr.{tsa_name}"

    with tempfile.TemporaryDirectory() as td:
        tsq_path = Path(td) / "request.tsq"
        # Build RFC 3161 request using openssl
        r = subprocess.run(
            ["openssl", "ts", "-query", "-data", str(file_path),
             "-no_nonce", "-sha256", "-out", str(tsq_path)],
            capture_output=True,
        )
        if r.returncode != 0:
            print(f"[ts-request] ERROR: openssl ts -query failed: {r.stderr.decode()[:200]}", file=sys.stderr)
            return None

        # Send request to TSA
        try:
            resp = requests.post(
                tsa_url,
                data=tsq_path.read_bytes(),
                headers={"Content-Type": "application/timestamp-query"},
                timeout=timeout,
            )
            resp.raise_for_status()
        except Exception as exc:
            print(f"[ts-request] ERROR: TSA request to {tsa_url} failed: {exc}", file=sys.stderr)
            return None

        sidecar.write_bytes(resp.content)
        print(f"[ts-request] ✓ {file_path.name} → {sidecar.name} ({len(resp.content)} bytes)")
        return sidecar


def _ts_verify(file_path: Path, tsr_path: Path, tsa_cert: str | None = None) -> bool:
    """Verify a TSR sidecar against the file using openssl ts -verify."""
    if not _openssl_available():
        print("[ts-request] ERROR: 'openssl' not found in PATH", file=sys.stderr)
        return False

    cmd = ["openssl", "ts", "-verify", "-data", str(file_path), "-in", str(tsr_path)]
    if tsa_cert:
        cmd += ["-CAfile", tsa_cert]
    else:
        # Without a TSA cert we can only check the message imprint
        cmd += ["-no_check_time"]

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        print(f"[ts-request] ✓ TSR valid: {tsr_path.name}")
        return True
    else:
        print(f"[ts-request] ✗ TSR invalid: {r.stderr.decode()[:200]}", file=sys.stderr)
        return False


def _harvest(alerts_dir: Path, since_minutes: int, tsa_url: str, tsa_name: str) -> int:
    """Timestamp all .cal files modified in the last N minutes that lack a TSR."""
    cutoff = time.time() - since_minutes * 60
    cal_files = sorted(alerts_dir.glob("*.cal"))
    pending = [
        p for p in cal_files
        if p.stat().st_mtime >= cutoff
        and not (p.parent / f"{p.name}.tsr.{tsa_name}").exists()
    ]
    if not pending:
        print(f"[ts-request] No pending .cal files (modified in last {since_minutes} min, no TSR)")
        return 0

    print(f"[ts-request] Harvesting {len(pending)} .cal file(s) → {tsa_name}")
    ok = 0
    for f in pending:
        if _ts_request(f, tsa_url, tsa_name):
            ok += 1
        time.sleep(0.5)  # Rate-limit courtesy for free TSA

    print(f"[ts-request] {ok}/{len(pending)} timestamped")
    return 0 if ok == len(pending) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")

    # Single file
    req_p = sub.add_parser("request", help="Timestamp a single file")
    req_p.add_argument("--file", type=Path, required=True)
    req_p.add_argument("--digicert", action="store_true", help="Also request from DigiCert")

    # Harvest
    har_p = sub.add_parser("harvest", help="Timestamp all recent .cal files without TSR")
    har_p.add_argument("--dir", type=Path, required=True, help="run/alerts/ directory")
    har_p.add_argument("--since-minutes", type=int, default=60)
    har_p.add_argument("--digicert", action="store_true")

    # Verify
    vfy_p = sub.add_parser("verify", help="Verify a TSR sidecar")
    vfy_p.add_argument("--file", type=Path, required=True)
    vfy_p.add_argument("--tsr", type=Path, required=True)
    vfy_p.add_argument("--tsa-cert", default=None, help="TSA CA cert PEM (optional)")

    # Legacy flat args (for Makefile compatibility)
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--harvest", type=Path, default=None)
    parser.add_argument("--since-minutes", type=int, default=60)
    parser.add_argument("--verify", type=Path, default=None)
    parser.add_argument("--tsr", type=Path, default=None)
    parser.add_argument("--tsa-cert", default=None)
    parser.add_argument("--digicert", action="store_true")

    args = parser.parse_args()

    # Flat mode (no subcommand)
    if args.cmd is None:
        if args.verify and args.tsr:
            ok = _ts_verify(args.verify, args.tsr, args.tsa_cert)
            return 0 if ok else 1
        if args.harvest:
            rc = _harvest(args.harvest, args.since_minutes, TSA_FREETSA, "freetsa")
            if args.digicert:
                rc2 = _harvest(args.harvest, args.since_minutes, TSA_DIGICERT, "digicert")
                return rc or rc2
            return rc
        if args.file:
            sidecar = _ts_request(args.file, TSA_FREETSA, "freetsa")
            if args.digicert:
                _ts_request(args.file, TSA_DIGICERT, "digicert")
            return 0 if sidecar else 1
        parser.print_help()
        return 2

    if args.cmd == "request":
        sidecar = _ts_request(args.file, TSA_FREETSA, "freetsa")
        if args.digicert:
            _ts_request(args.file, TSA_DIGICERT, "digicert")
        return 0 if sidecar else 1

    if args.cmd == "harvest":
        rc = _harvest(args.dir, args.since_minutes, TSA_FREETSA, "freetsa")
        if args.digicert:
            rc2 = _harvest(args.dir, args.since_minutes, TSA_DIGICERT, "digicert")
            return rc or rc2
        return rc

    if args.cmd == "verify":
        ok = _ts_verify(args.file, args.tsr, args.tsa_cert)
        return 0 if ok else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
