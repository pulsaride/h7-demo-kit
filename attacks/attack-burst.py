#!/usr/bin/env python3
"""
attack-burst.py — Rafale de connexions réseau (ADR-019 L4 demo).

Simule un agent LLM compromis qui génère un burst de connexions sortantes
anormal — signal NET_EGRESS_BURST (dépassement 4σ du taux de connexion
calibré).

Ce scénario démontre le second signal L4 (ADR-019 §3.3) :
  - Baseline calibrée : ~0.5 connexions/s vers le sinkhole 127.0.0.1:9999
  - Phase attaque : 50+ connexions/s → dépasse mu + 4σ
  → h7-brain émet : NET_EGRESS_BURST (enrichissement épisode actif)

Usage :
  python3 attacks/attack-burst.py
  python3 attacks/attack-burst.py --rate 80 --duration 15
  python3 attacks/attack-burst.py --target-host 127.0.0.1 --target-port 9999

Structure en deux phases (visible dans les logs) :
  Phase 1 — Baseline (10s) : trafic normal pour établir le contexte
  Phase 2 — Burst    (15s) : pic de connexions → BREACH

Garanties :
  - 100 % loopback
  - Aucune écriture disque
  - Compatible ECONNREFUSED (sonde eBPF capture le syscall connect)
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time


_BANNER = """
╔══════════════════════════════════════════════════════╗
║  H7 DEMO — BURST DE CONNEXIONS (ADR-019 L4)         ║
║  Canal : sys_enter_connect → NET_EGRESS_BURST 4σ    ║
╚══════════════════════════════════════════════════════╝
"""


def _single_connect(host: str, port: int) -> None:
    """Tentative de connexion TCP — le syscall connect() est ce qui compte."""
    try:
        with socket.create_connection((host, port), timeout=0.3):
            pass
    except OSError:
        pass  # ECONNREFUSED ou timeout — syscall capturé quand même


def _normal_phase(host: str, port: int, duration_s: float) -> None:
    """Phase 1 : trafic de référence (~0.5 conn/s)."""
    print(f"  Phase 1 — Baseline ({duration_s:.0f}s)  ~0.5 conn/s …", flush=True)
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        _single_connect(host, port)
        time.sleep(2.0)


def _burst_phase(host: str, port: int, rate: float, duration_s: float) -> None:
    """Phase 2 : rafale de connexions à <rate> conn/s."""
    print(f"  Phase 2 — BURST ({duration_s:.0f}s)  {rate:.0f} conn/s  "
          f"→ signal NET_EGRESS_BURST attendu", flush=True)
    interval = 1.0 / max(rate, 1.0)
    deadline = time.monotonic() + duration_s
    count = 0
    while time.monotonic() < deadline:
        t = threading.Thread(target=_single_connect, args=(host, port), daemon=True)
        t.start()
        count += 1
        time.sleep(interval)
    print(f"  Burst terminé — {count} connexions émises", flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Démo burst connexions L4 — NET_EGRESS_BURST")
    p.add_argument("--target-host", default="127.0.0.1")
    p.add_argument("--target-port", type=int, default=9999)
    p.add_argument("--rate", type=float, default=60.0,
                   help="Connexions/s pendant le burst (défaut 60, >> baseline 0.5/s)")
    p.add_argument("--baseline-duration", type=float, default=10.0,
                   help="Durée phase baseline en secondes (défaut 10)")
    p.add_argument("--burst-duration", type=float, default=15.0,
                   help="Durée phase burst en secondes (défaut 15)")
    args = p.parse_args()

    if args.target_host not in ("127.0.0.1", "::1", "localhost"):
        print(f"[burst] REFUS: --target-host doit être loopback", file=sys.stderr)
        return 2

    print(_BANNER)
    print(f"Cible  : {args.target_host}:{args.target_port}")
    print(f"Burst  : {args.rate:.0f} conn/s  (seuil attendu mu+4σ ≈ 4/s sur baseline calibrée)")
    print()

    _normal_phase(args.target_host, args.target_port, args.baseline_duration)
    _burst_phase(args.target_host, args.target_port, args.rate, args.burst_duration)

    print()
    print("─" * 60)
    print("Signal H7 attendu : NET_EGRESS_BURST → épisode BREACH")
    print("Vérification      : make verify-alert")
    print("Logs h7-brain     : grep NET_EGRESS_BURST run/logs/h7-brain.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
