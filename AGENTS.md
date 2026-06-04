# AI Agent Rules — h7-demo-kit

> **Hérite de la charte canonique CAE** : `../cae-research-kit/AGENTS.md` (7 règles de véracité + invariants techniques globaux). Ce fichier ajoute uniquement les règles spécifiques à ce repo.

Démo reproductible H7 (calibration, télémétrie, gate hardening). Tout doit tourner offline et fail-closed.

## Invariants (NEVER break)

1. **Stdlib-only pour les scripts de démo** (`scripts/sim-live-telemetry.py`, `scripts/seed-offline-baseline.py`). Pas de dépendance pip dans le chemin démo critique.
2. **Schéma AlertCert v1.1 gelé** (`docs/schemas/alert-v1.1.json`). Tout champ ajouté = ADR + bump v1.2.
3. **Baseline canonique.** Le hash SHA-256 de la baseline exclut la clé `sha256` elle-même. Ne pas changer l'algo de canonicalisation sans ADR.
4. **Fallback BTF automatique.** `make calibrate` doit :
   - skip si baseline non-pending,
   - sinon si `/sys/kernel/btf/vmlinux` absent → `seed-offline-baseline`,
   - sinon → calibration sensor live (sudo).
5. **Pinned signing key.** `fixtures/H7_RELEASE_SIGNING.pub` est la seule source de vérité pour la vérif release. Jamais de fetch réseau.
6. **Aucun repo imbriqué.** `h7-monitor` est un sibling, jamais un sous-dossier. `H7_MONITOR_BACKEND_DIR` pointe par défaut vers `../h7-monitor/backend`.
7. **Stdlib-only pour `attacks/`**. Les scripts `attacks/attack-*.py` n'utilisent que la stdlib Python (socket, ctypes, threading, urllib.request). Pas de `import requests`, `import httpx`, ni aucune dépendance pip. Même règle que `scripts/` pour le chemin démo critique.
8. **Loopback strict pour `attacks/`**. Toute connexion réseau dans `attacks/` doit vérifier explicitement que `--attacker-host` / `--target-host` est `127.0.0.1`, `::1` ou `localhost` avant d'émettre un syscall. Fail-closed avec code 2 si la vérification échoue.
9. **Canaux de détection couverts.** Le kit doit démontrer les 5 canaux H7 : (L1) κ/CUSUM via `make attack`, (L2) LLM_AGENT_HIJACK via `make attack-vercel`, (L3) BGTE implicite dans tous les scénarios, (L4) réseau via `make attack-exfil` / `attack-burst`, (L5) ptrace via `make attack-ptrace`. Toute nouvelle classe de menace (`threat_class`) doit avoir un scénario démo associé dans `attacks/` ou `scripts/`.

## Tests obligatoires avant push

```bash
make verify-gate-hardening       # 3/3 OK requis
python3 scripts/sim-live-telemetry.py --duration-sec 4 --interval-ms 500  # NDJSON valide
make seed-offline-baseline       # idempotent

# Smoke-test syntaxe nouveaux scénarios (stdlib only, pas de sudo requis)
python3 -m py_compile attacks/attack-exfil.py attacks/attack-burst.py attacks/attack-ptrace.py
python3 attacks/attack-exfil.py --count 1 --interval 0   # attend ECONNREFUSED — OK
python3 attacks/attack-ptrace.py --dry-run                # aucun syscall réel
```

## Discipline Makefile

- `.PHONY` à jour pour toute nouvelle cible.
- Commentaires `## help text` sur chaque cible publique (self-documenting).
- Pas de `sudo` implicite hors `calibrate`.

## Interdictions

- ❌ Ajouter `requirements.txt` runtime pour les scripts démo (seuls les tests/CI peuvent dépendre de pip).
- ❌ Supprimer les vérifications path-traversal de `verify-gate-hardening.py`.
- ❌ Réécrire des fixtures signées existantes.
- ❌ Hard-coder un chemin absolu vers `h7-monitor` (toujours via env var).
- ❌ Ajouter `Co-Authored-By:` ou toute mention d'agent/IA dans les messages de commit. Les commits doivent être signés sous l'identité de l'auteur humain uniquement.
- ❌ Utiliser une IP non-loopback dans `attacks/` — même pour un test de portée (`0.0.0.0`, IPs publiques). Toujours vérifier et fail avec code 2.
- ❌ Ajouter un scénario d'attaque qui spawne un shell réel (`subprocess.run(["bash", ...])`) — les scénarios doivent simuler le comportement de l'attaquant via des syscalls directs (socket, ctypes.ptrace), pas via des shell intermédiaires.
