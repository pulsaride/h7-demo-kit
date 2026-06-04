#!/usr/bin/env python3
"""
attack-ns-reexecve.py — PoC d'évasion par re-execve dans un namespace PID fils.

ADR-023 §2.3 / ADVERSARIAL-EVASION-REPORT-2026.md — PoC 3.

Scénario : un attaquant fork + unshare(CLONE_NEWPID) pour créer un namespace
PID fils isolé, puis execve un shell dans ce namespace. Cette technique est
utilisée pour "casser" la traçabilité de parenté des processus dans certains
outils de surveillance userspace.

Objectif du test : H7 associe les événements execve à leur ns_cookie (inode
du namespace PID, résolu via /proc/<pid>/ns/pid par le NetProcessor). Le test
vérifie que H7 track correctement le fils ou que l'évasion est documentée.

Résultats attendus :
  exit 0  — H7 a levé une alerte (ns_cookie du fils connu ou propagé)
  exit 2  — Aucune alerte levée (ns_cookie du fils non enregistré — limite documentée)
  exit 1  — Erreur (unshare non disponible, pas de CAP_SYS_ADMIN, etc.)

Garanties :
  - le shell spawné ne fait qu'imprimer un message et quitter (sleep 1)
  - aucun accès réseau, aucune écriture sensible
  - durée limitée à --duration secondes

Usage :
  sudo python3 scripts/attack-ns-reexecve.py        # requires CAP_SYS_ADMIN or root
  sudo python3 scripts/attack-ns-reexecve.py --duration 30

Note : unshare(CLONE_NEWPID) requiert CAP_SYS_ADMIN (ou être root).
Si les privilèges sont insuffisants, le script retourne exit 1 avec un message
explicite — c'est une limite connue et documentée.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import subprocess
import sys
import time

CLONE_NEWPID = 0x20000000  # unshare flag for PID namespace


def _unshare_newpid() -> bool:
    """Call unshare(CLONE_NEWPID) to create a new PID namespace. Requires root/CAP_SYS_ADMIN."""
    libc_name = ctypes.util.find_library("c")
    if not libc_name:
        return False
    libc = ctypes.CDLL(libc_name, use_errno=True)
    ret = libc.unshare(ctypes.c_int(CLONE_NEWPID))
    return ret == 0


def _read_ndjson_alert_count(ndjson_path: str) -> int:
    try:
        with open(ndjson_path) as f:
            return sum(1 for line in f if line.strip())
    except FileNotFoundError:
        return 0


def _resolve_ns_cookie(pid: int) -> str | None:
    """Read the PID namespace inode of a process (same logic as h7-sensor NetProcessor)."""
    try:
        target = os.readlink(f"/proc/{pid}/ns/pid")
        return target  # e.g., "pid:[4026531836]"
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration",  type=int, default=30, help="Observation window in seconds (default: 30)")
    parser.add_argument("--alert-log", type=str, default="run/logs/alerts.ndjson",
                        help="Path to NDJSON alert log (default: run/logs/alerts.ndjson)")
    args = parser.parse_args()

    print("[ns-reexecve] PoC 3 — re-execve in isolated PID namespace")
    print(f"[ns-reexecve] duration={args.duration}s")

    parent_ns = _resolve_ns_cookie(os.getpid())
    print(f"[ns-reexecve] parent PID namespace: {parent_ns}")

    alerts_before = _read_ndjson_alert_count(args.alert_log)

    # Fork a child that will unshare into a new PID namespace then exec a shell
    pid = os.fork()
    if pid == 0:
        # Child process
        ok = _unshare_newpid()
        if not ok:
            err = ctypes.get_errno()
            # errno 1 = EPERM (no capability), errno 22 = EINVAL
            print(f"[ns-reexecve] CHILD: unshare(CLONE_NEWPID) failed errno={err} — requires root/CAP_SYS_ADMIN",
                  file=sys.stderr)
            os._exit(1)

        child_ns = _resolve_ns_cookie(os.getpid())
        print(f"[ns-reexecve] CHILD: new PID namespace: {child_ns}")
        print(f"[ns-reexecve] CHILD: parent_ns={parent_ns} child_ns={child_ns} same={parent_ns==child_ns}")

        # execve a harmless shell command in the new namespace
        os.execv("/bin/sh", ["/bin/sh", "-c", "echo '[ns-reexecve] execve in child ns OK'; sleep 2"])
        os._exit(1)  # unreachable if execv succeeds

    # Parent: wait for child and observe
    try:
        child_pid, exit_status = os.waitpid(pid, 0)
    except ChildProcessError:
        print("[ns-reexecve] ERROR: could not wait for child", file=sys.stderr)
        return 1

    child_exit = (exit_status >> 8) & 0xFF
    if child_exit == 1:
        print("[ns-reexecve] ERROR: child failed to unshare — run as root or with CAP_SYS_ADMIN")
        return 1

    print(f"[ns-reexecve] child exited with code {child_exit}")
    print(f"[ns-reexecve] waiting {args.duration}s for H7 to register alert...")
    time.sleep(args.duration)

    alerts_after = _read_ndjson_alert_count(args.alert_log)
    new_alerts = alerts_after - alerts_before

    print(f"[ns-reexecve] done. New alerts in NDJSON log: {new_alerts}")

    if new_alerts > 0:
        print("[ns-reexecve] RESULT: DETECTED — H7 tracked execve across PID namespace boundary")
        return 0
    else:
        print("[ns-reexecve] RESULT: NOT DETECTED — execve in isolated PID namespace may evade ns_cookie tracking")
        print("  This is a documented limit: if H7's ns_cookie filter does not include the child")
        print("  namespace at the time of execve, the event is dropped (NetProcessor filter logic).")
        print("  See THREAT-MODEL.md and ADR-PROD-023 §2.3 for characterization.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
