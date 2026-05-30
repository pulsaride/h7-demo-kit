#!/usr/bin/env python3
"""
attack-noise.py — générateur de charge `sched_switch` pour la démo H7.

PLAN-STRATEGIQUE-v2 §4.1 livrable T5. **Pas un malware** : juste un worker
multi-thread qui sature le scheduler pour franchir le seuil κ + CUSUM
calibré dans la baseline. Optionnellement envoie un faux « beacon » HTTP
au sinkhole loopback pour démontrer la capture défensive.

Mode --vercel-pattern (veille 2026-05-21) : reconstitue le profil de
charge observé lors du pivot supply-chain Vercel/Context.ai du 21 avril
2026 — burst initial de forks courts (reconnaissance), puis charge
soutenue plus modérée (exfiltration). Reste purement local et défensif :
aucun fichier système réel n'est lu, aucun trafic ne quitte le loopback.
Voir `docs/case-studies/VERCEL-2026-04-21.md`.

Usage :
  python3 scripts/attack-noise.py
  python3 scripts/attack-noise.py --duration 60 --workers 4
  python3 scripts/attack-noise.py --beacon-url http://127.0.0.1:9999/exfil
  python3 scripts/attack-noise.py --vercel-pattern --beacon-url http://127.0.0.1:9999/exfil

Garanties :
  - aucune écriture disque
  - aucun appel réseau autre que --beacon-url (loopback only check)
  - se termine proprement après --duration secondes
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
import threading
import time
import urllib.request  # MUST be top-level: importing from beacon_loop() inside
# a non-main thread deadlocks on Python's import lock when cpu_burn threads
# hold the GIL tightly. Incident 2026-05-22: 0 beacon reached sinkhole.
from urllib.parse import urlparse


def cpu_burn(stop_evt: threading.Event) -> None:
    """Boucle CPU + nombreux yields pour générer des sched_switch."""
    x = 0
    while not stop_evt.is_set():
        for _ in range(2000):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        # yield explicite : le scheduler est forcé de switcher.
        os.sched_yield()


def _vercel_burst_worker(burst_seconds: float) -> None:
    """Worker dédié (process spawné) : rafale fork/waitpid.

    Doit tourner dans un process *isolé* du process principal, sinon
    `os.fork()` depuis un thread du parent corrompt la `beacon_loop`
    (GIL + urllib locks ⇒ deadlock du POST sinkhole). Voir incident
    démo 2026-05-22 : 820 alertes mais sinkhole.ndjson vide.
    """
    deadline = time.monotonic() + burst_seconds
    while time.monotonic() < deadline:
        try:
            pid = os.fork()
        except OSError:
            os.sched_yield()
            continue
        if pid == 0:
            os._exit(0)
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass


def start_vercel_burst(burst_seconds: float = 8.0) -> mp.Process:
    """Démarre le burst dans un process spawné (pas fork depuis thread).

    Reconstitue le profil pivot supply-chain Vercel/Context.ai
    (2026-04-21) : burst fork/waitpid ~8s puis retour au régime soutenu
    porté par les workers CPU. Garantit que le process principal qui
    porte la `beacon_loop` reste mono-process clean.
    """
    ctx = mp.get_context("spawn")
    proc = ctx.Process(
        target=_vercel_burst_worker, args=(burst_seconds,), name="vercel-burst", daemon=True
    )
    proc.start()
    return proc


def beacon_loop(url: str, stop_evt: threading.Event, period_s: float = 2.0) -> None:
    """Envoie un faux beacon HTTP au sinkhole, période lente (démo).

    `urllib.request` est importé au top du module : importer depuis ici
    (thread non-main) deadlocke quand cpu_burn tient le GIL. Cf. incident
    2026-05-22 (sinkhole.ndjson vide alors que 820 alertes).
    """
    parsed = urlparse(url)
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"[attack-noise] REFUS beacon : {url} non-loopback. Ce script est local.",
            file=sys.stderr,
        )
        return
    payload = b'{"sim":"h7-demo","beacon":1}'
    req_template = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "h7-demo-attack/1.0"},
    )
    while not stop_evt.is_set():
        try:
            urllib.request.urlopen(req_template, timeout=1.0).read()
        except Exception as e:  # pragma: no cover — démo
            print(f"[attack-noise] beacon fail (sinkhole down ?): {e}", file=sys.stderr)
        stop_evt.wait(period_s)


def main() -> int:
    p = argparse.ArgumentParser(description="Générateur de charge sched_switch (démo H7).")
    p.add_argument("--duration", type=int, default=60, help="Durée en secondes (défaut 60).")
    p.add_argument("--workers", type=int, default=4, help="Threads CPU concurrents (défaut 4).")
    p.add_argument(
        "--beacon-url",
        default=None,
        help="Si fourni, envoie un faux beacon vers cette URL loopback toutes les 2s.",
    )
    p.add_argument(
        "--vercel-pattern",
        action="store_true",
        help="Active le profil de pivot supply-chain Vercel/Context.ai (2026-04-21).",
    )
    args = p.parse_args()

    if args.workers < 1 or args.workers > 64:
        print(f"[attack-noise] --workers hors plage : {args.workers}", file=sys.stderr)
        return 2
    if args.duration < 1 or args.duration > 600:
        print(f"[attack-noise] --duration hors plage : {args.duration}", file=sys.stderr)
        return 2

    stop_evt = threading.Event()
    threads: list[threading.Thread] = []
    burst_proc: mp.Process | None = None
    if args.vercel_pattern:
        burst_proc = start_vercel_burst(burst_seconds=8.0)
        print(
            "[attack-noise] mode --vercel-pattern : burst fork/waitpid 8s (process spawné) puis charge soutenue",
            file=sys.stderr,
        )
    for i in range(args.workers):
        t = threading.Thread(target=cpu_burn, args=(stop_evt,), name=f"burn-{i}", daemon=True)
        t.start()
        threads.append(t)
    if args.beacon_url:
        t = threading.Thread(
            target=beacon_loop, args=(args.beacon_url, stop_evt), name="beacon", daemon=True
        )
        t.start()
        threads.append(t)

    print(
        f"[attack-noise] up : {args.workers} workers, durée {args.duration}s"
        + (f", beacon → {args.beacon_url}" if args.beacon_url else ""),
        file=sys.stderr,
    )
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        print("[attack-noise] interrupt", file=sys.stderr)
    finally:
        stop_evt.set()
        for t in threads:
            t.join(timeout=1.0)
        if burst_proc is not None and burst_proc.is_alive():
            burst_proc.terminate()
            burst_proc.join(timeout=2.0)
    print("[attack-noise] done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
