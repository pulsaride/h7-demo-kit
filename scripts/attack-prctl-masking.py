#!/usr/bin/env python3
"""
attack-prctl-masking.py — PoC d'évasion par masquage du nom de processus.

ADR-023 §2.3 / ADVERSARIAL-EVASION-REPORT-2026.md — PoC 2.

Scénario : un agent compromis renomme son thread via prctl(PR_SET_NAME) pour
qu'il apparaisse comme un processus bénin ("kworker", "python3", etc.) dans
les journaux applicatifs et les outils de surveillance de l'espace utilisateur.
Simultanément, il maintient une pression CPU pour franchir le seuil κ/CUSUM.

Objectif du test : H7 observe sched_switch au niveau noyau — il ne se fie pas
au nom de processus exposé par /proc/<pid>/comm (falsifiable via prctl). Le
test vérifie que le canal L1 (entropie d'ordonnancement κ) détecte la charge
même si le nom du thread est usurpé.

Résultats attendus :
  exit 0  — H7 a levé une alerte (canal L1 indépendant du nom du processus)
  exit 2  — Aucune alerte levée dans la fenêtre d'observation (évasion partielle)
  exit 1  — Erreur d'exécution (prctl non disponible, etc.)

Garanties :
  - aucune écriture disque
  - aucun appel réseau
  - se termine proprement après --duration secondes
  - ne nécessite pas de privilèges root

Usage :
  python3 scripts/attack-prctl-masking.py
  python3 scripts/attack-prctl-masking.py --duration 60 --workers 4
  python3 scripts/attack-prctl-masking.py --fake-name "kworker/0:1"
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import sys
import threading
import time

PR_SET_NAME    = 15   # prctl option: set thread name (max 16 bytes incl. NUL)
PR_SET_DUMPABLE = 4   # prctl option: disable core dump (reduces audit visibility)


def _prctl(option: int, arg: int | bytes) -> int:
    libc_name = ctypes.util.find_library("c")
    if not libc_name:
        return -1
    libc = ctypes.CDLL(libc_name, use_errno=True)
    if isinstance(arg, bytes):
        return libc.prctl(option, arg, 0, 0, 0)
    return libc.prctl(option, ctypes.c_ulong(arg), 0, 0, 0)


def _set_thread_name(name: str) -> bool:
    """Set the current thread name via prctl(PR_SET_NAME). Returns True on success."""
    encoded = name.encode("utf-8")[:15] + b"\x00"
    ret = _prctl(PR_SET_NAME, encoded)
    return ret == 0


def cpu_burn(stop_evt: threading.Event, fake_name: str) -> None:
    """CPU-intensive loop with a spoofed thread name."""
    _set_thread_name(fake_name)
    x = 0
    while not stop_evt.is_set():
        for _ in range(2000):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        os.sched_yield()


def _check_prctl_available() -> bool:
    try:
        return _prctl(PR_SET_NAME, b"h7-prctl-test\x00") == 0
    except Exception:
        return False


def _read_ndjson_alert_count(ndjson_path: str) -> int:
    try:
        with open(ndjson_path) as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration",   type=int,   default=60,         help="Duration in seconds (default: 60)")
    parser.add_argument("--workers",    type=int,   default=4,          help="CPU worker threads (default: 4)")
    parser.add_argument("--fake-name",  type=str,   default="kworker/0:1", help="Thread name to spoof")
    parser.add_argument("--alert-log",  type=str,   default="run/logs/alerts.ndjson",
                        help="Path to NDJSON alert log to count alerts (default: run/logs/alerts.ndjson)")
    args = parser.parse_args()

    print(f"[prctl-masking] PoC 2 — thread name spoofing + CPU load")
    print(f"[prctl-masking] duration={args.duration}s  workers={args.workers}  fake-name={args.fake_name!r}")

    if not _check_prctl_available():
        print("[prctl-masking] ERROR: prctl(PR_SET_NAME) not available on this platform", file=sys.stderr)
        return 1

    # Optionally suppress core dumps to further reduce audit visibility
    _prctl(PR_SET_DUMPABLE, 0)
    print(f"[prctl-masking] PR_SET_DUMPABLE=0 (core dump disabled)")
    print(f"[prctl-masking] spoofing thread names to {args.fake_name!r} via prctl(PR_SET_NAME)")
    print(f"[prctl-masking] H7 should detect via kernel sched_switch — NOT via /proc/<pid>/comm")

    alerts_before = _read_ndjson_alert_count(args.alert_log)

    stop = threading.Event()
    workers = [
        threading.Thread(target=cpu_burn, args=(stop, args.fake_name), daemon=True)
        for _ in range(args.workers)
    ]
    for w in workers:
        w.start()

    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for w in workers:
            w.join(timeout=2)

    alerts_after = _read_ndjson_alert_count(args.alert_log)
    new_alerts = alerts_after - alerts_before

    print(f"[prctl-masking] done. New alerts in NDJSON log: {new_alerts}")

    if new_alerts > 0:
        print("[prctl-masking] RESULT: DETECTED — H7 L1 fired despite thread name spoofing (expected)")
        return 0
    else:
        print("[prctl-masking] RESULT: NOT DETECTED — check baseline calibration and sensor status")
        print("  Possible causes: baseline too high, sensor not running, alert log path wrong")
        return 2


if __name__ == "__main__":
    sys.exit(main())
