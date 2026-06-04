#!/usr/bin/env python3
"""
attack-ptrace.py — Injection via ptrace(PTRACE_ATTACH) (Sprint 3 R-04 demo).

Simule un agent LLM compromis qui tente d'attacher un débogueur à un
processus cible via ptrace — vecteur d'injection de code avancé.

Ce scénario démontre le canal Sprint 3 (sys_enter_ptrace) :
  → h7-brain émet : PTRACE_ATTACK (confiance 0.85, BREACH immédiat)
    pour tout namespace marqué is_ai_runtime.

Usage :
  python3 attacks/attack-ptrace.py                  # s'attache à lui-même (fork)
  python3 attacks/attack-ptrace.py --target-pid PID # cible un PID existant
  python3 attacks/attack-ptrace.py --dry-run        # affiche seulement la logique

Pourquoi ptrace ?
  Un adversaire sophistiqué peut utiliser ptrace pour :
  1. Lire la mémoire d'un autre processus (exfil de clés/tokens en RAM)
  2. Injecter du code dans un processus en cours d'exécution
  3. Tracer les syscalls d'un processus cible sans execve

La sonde eBPF sys_enter_ptrace capture PTRACE_ATTACH (16) et
PTRACE_SEIZE (0x4206) — les deux primitives d'attachement.

Sécurité démo :
  - L'attachement réel est rejeté par le kernel si PTRACE_SCOPE=1 (défaut Ubuntu)
    → le syscall est quand même émis et capturé par h7-sensor
  - Aucune modification de processus en cas d'échec kernel
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import sys
import time

# PTRACE_ATTACH = 16 (POSIX), PTRACE_DETACH = 17
PTRACE_ATTACH = 16
PTRACE_DETACH = 17
PTRACE_SEIZE  = 0x4206

_BANNER = """
╔══════════════════════════════════════════════════════╗
║  H7 DEMO — PTRACE ATTACH (Sprint 3 R-04)            ║
║  Canal : sys_enter_ptrace → PTRACE_ATTACK (0.85)    ║
╚══════════════════════════════════════════════════════╝
"""


def _load_libc() -> ctypes.CDLL:
    path = ctypes.util.find_library("c")
    if not path:
        raise RuntimeError("libc introuvable")
    lib = ctypes.CDLL(path, use_errno=True)
    lib.ptrace.restype = ctypes.c_long
    lib.ptrace.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    return lib


def _ptrace_attach(libc: ctypes.CDLL, pid: int) -> tuple[int, str]:
    """Appelle ptrace(PTRACE_ATTACH, pid, 0, 0) — le syscall est ce qui est capturé."""
    ret = libc.ptrace(PTRACE_ATTACH, pid, None, None)
    err = ctypes.get_errno()
    if ret == 0:
        return 0, "succès"
    elif err == 1:  # EPERM
        return err, "EPERM — refusé kernel (PTRACE_SCOPE) [syscall capturé quand même ✓]"
    elif err == 3:  # ESRCH
        return err, "ESRCH — PID inexistant [syscall capturé quand même ✓]"
    else:
        return err, f"errno={err}"


def _ptrace_detach(libc: ctypes.CDLL, pid: int) -> None:
    libc.ptrace(PTRACE_DETACH, pid, None, None)


def _attach_to_child(libc: ctypes.CDLL) -> None:
    """Fork un enfant dormant et tente de l'attacher.

    Le fork crée un vrai PID de processus — cible valide pour ptrace.
    L'enfant dort 2s puis se termine proprement.
    """
    child_pid = os.fork()
    if child_pid == 0:
        # Enfant : dort 2 secondes pour être une cible valide
        time.sleep(2.0)
        os._exit(0)

    time.sleep(0.1)  # laisse le child s'initialiser
    ret, msg = _ptrace_attach(libc, child_pid)
    print(f"  ptrace(PTRACE_ATTACH, pid={child_pid}, 0, 0) → {msg}")

    if ret == 0:
        print(f"  ptrace(PTRACE_DETACH, pid={child_pid}, 0, 0) → nettoyage")
        _ptrace_detach(libc, child_pid)

    try:
        os.waitpid(child_pid, 0)
    except ChildProcessError:
        pass


def main() -> int:
    p = argparse.ArgumentParser(description="Démo ptrace attach — PTRACE_ATTACK")
    p.add_argument("--target-pid", type=int, default=None,
                   help="PID cible. Si absent : fork d'un enfant temporaire.")
    p.add_argument("--repeat", type=int, default=1,
                   help="Répéter N fois (défaut 1 — suffit pour déclencher le signal)")
    p.add_argument("--dry-run", action="store_true",
                   help="Affiche la logique sans appel syscall réel")
    args = p.parse_args()

    print(_BANNER)

    if args.dry_run:
        print("  [dry-run] Appel qui serait fait :")
        pid = args.target_pid or os.getpid()
        print(f"    libc.ptrace(PTRACE_ATTACH=16, pid={pid}, 0, 0)")
        print()
        print("  Signal H7 attendu : PTRACE_ATTACK → BREACH (confiance 0.85)")
        return 0

    try:
        libc = _load_libc()
    except RuntimeError as e:
        print(f"[ptrace] ERREUR: {e}", file=sys.stderr)
        return 1

    print(f"Tentatives ptrace : {args.repeat}")
    print(f"Cible             : {'fork temporaire' if args.target_pid is None else f'pid={args.target_pid}'}")
    print()

    for i in range(1, args.repeat + 1):
        print(f"  [{i}/{args.repeat}]", end=" ")
        if args.target_pid is not None:
            ret, msg = _ptrace_attach(libc, args.target_pid)
            print(f"ptrace(PTRACE_ATTACH, pid={args.target_pid}) → {msg}")
            if ret == 0:
                time.sleep(0.1)
                _ptrace_detach(libc, args.target_pid)
        else:
            _attach_to_child(libc)

        if i < args.repeat:
            time.sleep(0.5)

    print()
    print("─" * 60)
    print("Signal H7 attendu : PTRACE_ATTACK → BREACH (si namespace is_ai_runtime)")
    print("Vérification      : make verify-alert")
    print("Logs h7-brain     : grep PTRACE_ATTACK run/logs/h7-brain.log")
    print()
    print("Note : EPERM est attendu si /proc/sys/kernel/yama/ptrace_scope ≥ 1")
    print("       Le syscall est capturé dans tous les cas par h7-sensor.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
