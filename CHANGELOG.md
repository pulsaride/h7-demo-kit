# Changelog

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ;
versionnage [SemVer](https://semver.org/lang/fr/).

## [1.2.0] — 2026-06-04

### Added

- **Track D — h7ctl operator control plane** in docs and Make targets:
  - `make demo-ctl`
  - `make demo-evasion`
  - `make demo-siem`
- **`scripts/verify-baseline-sha256.py`**: validates self-referential SHA-256
  for both live-calibrated and offline-seeded baseline formats.
- **`scripts/demo-splunk-forward.py`**: tails NDJSON telemetry and forwards
  events to Splunk HEC.

### Changed

- **`verify-baseline`** target now uses local baseline hash verification script
  (does not require `h7` CLI verification path).
- **README / USER-GUIDE** now document Track D usage and local-path h7ctl mode.

### Notes

- Track D is designed for local evaluation paths (`run/`) and avoids requiring
  writes under `/etc` and `/var/lib`.

---

## [1.1.0] — 2026-06-02

### Changed

- **Binaries** : updated to `pulsaride/p-h7 v0.8.0` — h7-sensor + h7 CLI.
  Release assets on `pulsaride/h7-demo-kit` refreshed; `make setup` fetches
  the latest automatically.

- **`attack-vercel.sh`** : aligned with `make attack-vercel` Makefile target
  (canonical entry point for the CI/CD compromise scenario).

- **`KIT_CONTENTS`** on `pulsaride.com/demo-kit` updated to reflect actual
  repo structure (`agents/`, `scripts/`, `fixtures/`, `Makefile` targets).

---

## [0.9.0] — 2026-05-29

### Added

- **`tests/` pytest suite** (42 tests, ~12 s, no kernel/network required):
  - `test_baseline.py` — canonical hash algorithm, idempotence,
    fail-closed on missing fixture, `calibration_source` metadata.
  - `test_telemetry.py` — AlertCert v1.1 schema conformance, kappa bounds,
    tick monotonicity, CLI contract (`--duration-sec`, `--interval-ms`).
  - `test_schema.py` — frozen schema completeness, `additionalProperties:
    false` invariant, fixture integrity, mandatory document presence.
  - `test_repo_integrity.py` — all mandatory scripts/docs/fixtures present,
    no broken cross-repo references, correct CLI flags in `AGENTS.md`.
  - `conftest.py` — shared path constants.

- **`THREAT-MODEL.md`** : full adversary-profile threat model —
  §2 Trust Boundaries (host, network, schema, crypto attestation chain),
  §3 Attack Surface table (path-traversal, CORS, tamper, baseline
  poisoning, key exfiltration), §4 Adversary Profiles ADV-1–ADV-4
  (including §4.3 ADV-3 adaptive κ evasion acknowledged in VDP),
  §5 Out of Scope, §6 Assumptions and Non-Goals.

- **`docs/BUG-BOUNTY-PROGRAM.md`** : in-repo bug bounty scope, reward
  tiers, and disclosure timeline (replaces broken cross-repo link).

- **`USER-GUIDE.md`** : comprehensive step-by-step guide covering Docker
  quick-start, sensor demo (Parts 1–2), K8s demo (Part 3), compliance
  evidence packages (Part 4), test suite (Part 5), offline/air-gapped
  operation (Part 6), troubleshooting table (Part 7), key files reference
  (Part 8), and "what the kit proves" summary (Part 9).

- **`CONTRIBUTING.md`** : contributor workflow — hard constraints (stdlib-
  only scripts, frozen schema, no nested repos), development workflow
  (`make test` + mandatory pre-push checks), commit style, new-script and
  new-doc checklists.

- **`CODE_OF_CONDUCT.md`** : Contributor Covenant 2.1.

- **`docs/demo/DEMO-SNAPSHOT.md`** : annotated NDJSON telemetry snapshot
  across all three signal phases (Phase A nominal, Phase B breach ramp,
  Phase C exponential recovery) with schema and cryptographic attestation
  commentary.

- **`make test` Makefile target** : runs `pytest tests/ -v`; added to
  `.PHONY`.

### Fixed

- **`AGENTS.md`** : corrected mandatory pre-push invocation —
  `--duration 4 --rate 2` → `--duration-sec 4 --interval-ms 500`
  (flags that do not exist were documented). Gate count corrected:
  `2/2 OK` → `3/3 OK` (reflects actual `verify-gate-hardening.py`
  output).

- **`SECURITY.md`** : replaced broken cross-repo link
  `../PulsarideShield/pulsaride-h7/docs/BUG-BOUNTY-PROGRAM.md` with
  in-repo `docs/BUG-BOUNTY-PROGRAM.md`. Updated `THREAT-MODEL.md §4.3`
  reference to a proper anchor link.

- **`docs/runbook.md`** : removed broken cross-repo reference to
  `../../PulsarideShield/VIDEO-YOUTUBE-DEMO.md`; replaced with link to
  in-repo `USER-GUIDE.md`.

### Changed

- **CI** (`.github/workflows/e2e.yml`) : added `make test` step
  (pure-Python pytest suite, no external services) as an independent job
  that runs in parallel with `e2e-full`. Pinned `pytest` installation.
  Added `make seed-offline-baseline` step for reproducible BTF-less CI.

---

## [0.8.0] — 2026-05-26

### Added

- **Demo 2 — K8s Attack** (`launch-k8s-demo.sh`) : démo 7 phases avec un
  vrai cluster Kind (Docker, zero-cloud). Prouve ADR-014 `k8s_watcher` :
  - Phase 1 : `kind create cluster --name h7-sandbox` (~30 s avec image cachée).
  - Phase 2 : h7-brain (`:7700`, `KUBECONFIG` Kind) + h7-monitor (`:8000`) +
    Next.js (`:3001`).
  - Phase 3 : déploiement `langchain-agent` avec annotations
    `pulsaride.io/is-ai-runtime: "true"`.
  - Phase 4 : `kubectl exec readlink /proc/self/ns/pid` → ns_cookie entier →
    annotation pod → `POST /namespaces/{cookie}?service_tag=...`.
  - Phase 5 : baseline — pod logs montrent des prompts légitimes.
  - Phase 6 : `kubectl exec /bin/bash` (vrai shell dans le pod K8s) + debug inject.
  - Phase 7 : cascade BREACH `LLM_AGENT_HIJACK`, `/agents` unifié 2 canaux,
    rapport DORA/NIS2 (`certificate.verified: true`).
  - Cleanup automatique : `kind delete cluster` à Ctrl-C.
  - Banner final : 4 URLs exposées (`:3001` UI, `:8000/agents` API,
    `:7700/fleet`, `:7700/reports/dora`).

- **`k8s/langchain-agent-pod.yaml`** : manifest Pod avec annotations
  `pulsaride.io/is-ai-runtime`, `pulsaride.io/service-tag`,
  `pulsaride.io/environment` ; simule un agent LangChain en idle loop.

- **`k8s/h7-rbac.yaml`** : `ClusterRole` `h7-brain-watcher`
  (get/list/watch/patch pods) + `ClusterRoleBinding` vers `kubernetes-admin`.

- **Demo 1 — Vercel Attack** (`attack-vercel.sh`) : démo 5 phases complète
  (de `v0.7.2`, documentée ici pour la première fois dans le CHANGELOG) :
  - Phase 1 : infrastructure h7-brain + h7-monitor + Next.js.
  - Phase 2 : boot `agents/vercel_agent.py` (LangChain simulé).
  - Phase 3 : baseline κ/CUSUM NDJSON (3 ticks nominaux).
  - Phase 4 : ENTER → trigger `ATTACK_TRIGGER` → `subprocess /bin/bash` dans
    le process agent → debug inject QII frame → κ/CUSUM spike NDJSON.
  - Phase 5 : détection BREACH `LLM_AGENT_HIJACK`, rapport DORA/NIS2.

- **`agents/vercel_agent.py`** : agent LangChain simulé, surveille un fichier
  `ATTACK_TRIGGER`, déclenche `subprocess.run(["/bin/bash", ...])` à la
  détection ; reste en idle loop post-attaque.

### Changed

- **README** : refonte complète — 2 demos documentés, architecture 3-tiers,
  prérequis séparés par demo, table "what the demos prove", limitations
  honnêtes (k8s_watcher node filter, mock vs real malware).

### Fixed

- Banner `launch-k8s-demo.sh` : ajout de `h7-monitor API :8000/agents` et
  `h7-monitor API :8000/audit` (le backend était lancé mais invisible dans
  le banner final).

---

## [0.7.2] — 2026-05-24

- `attack-vercel.sh` : fix EPISODE_ID filtre sur `threat_class == 'LLM_AGENT_HIJACK'`
  (deux épisodes concurrents possibles quand mock-qii est actif).
- `attack-vercel.sh` : suppression de `--mock-qii` du lancement h7-sensor
  (créait des épisodes `UNKNOWN_ANOMALY` parasites sur `/usr/bin/python3`).
- `attack-vercel.sh` : `export TERM="${TERM:-xterm-256color}"` pour exécution
  non-interactive.

## [0.7.1] — 2026-05-22

- Schéma d'alerte v1.1 figé : [`docs/schemas/alert-v1.1.json`](docs/schemas/alert-v1.1.json).
- DORA/NIS2 checklist : [`docs/DORA-NIS2-CHECKLIST.md`](docs/DORA-NIS2-CHECKLIST.md).
- EU AI Act traceability : [`docs/EU-AI-ACT-TRACEABILITY.md`](docs/EU-AI-ACT-TRACEABILITY.md).
- GTM kit : [`docs/gtm/`](docs/gtm/).
- CI e2e workflow (`.github/workflows/`).
- `AGENTS.md` : charte AI — interdiction attribution dans les commits.
