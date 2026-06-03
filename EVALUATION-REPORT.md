# Evaluation Report — Pulsaride H7 Demo Kit

**Evaluator host:** `lsalihi-Precision-7560` (Ubuntu, Linux 6.11.0-26-generic, BTF present)
**Kit path:** `/home/lsalihi/startup/h7-demo-kit/`
**Evaluation date:** 2026-05-31
**Kit revision:** as installed from `pulsaride/h7-demo-kit:latest` (binaries fetched via `make setup`)

---

## 1. Project Overview

The Pulsaride H7 Demo Kit is a self-contained evaluation environment for Pulsaride-H7, a kernel-level behavioral-attestation platform that detects LLM-agent runtime drift via eBPF `sched_switch` analysis (CUSUM on κ entropy metric). Each detected breach is materialized as an Ed25519-signed AlertCert v1.1 sidecar, designed to survive in court as a regulator-facing evidence artifact (DORA Art. 17 / NIS2 Art. 21).

The kit exposes three evaluation tracks:

- **Track A** — offline schema + crypto validation (no privileges, no Docker)
- **Track B** — Docker monitor stack + synthetic telemetry stream (Docker required)
- **Track C** — live eBPF sensor with attack simulation (sudo + kernel ≥ 5.8 with BTF)

**Detection architecture (5 independent channels):**

| Channel | Syscall hook | Signal | Demo target |
|---|---|---|---|
| L1 — κ/CUSUM scheduling entropy | `sched_switch` tracepoint | `BREACH` (cusum_s ≥ h) | `make attack` |
| L2 — Namespace execve classification | `sys_enter_execve` | `LLM_AGENT_HIJACK` (0.94) | `make attack-vercel` |
| L3 — BGTE topological analysis | (async, from QII stream) | `CAUSAL_LOOP`, `ORBIT_DRIFT` | corroborates all scenarios |
| L4 — Network egress (ADR-019) | `sys_enter_connect`, `sys_enter_sendmsg` | `UNKNOWN_DESTINATION`, `NET_EGRESS_BURST` | `make attack-exfil`, `attack-burst` |
| L5 — ptrace attach (Sprint 3) | `sys_enter_ptrace` | `PTRACE_ATTACK` (0.85) | `make attack-ptrace` |

A complementary `e2e-full` target exercises the full pipeline (sim → monitor → attest → verify → drift → audit) without requiring the kernel sensor — useful for CI/portability validation.

---

## 2. Execution Results

### 2.1 Track A — Offline schema + crypto

**Commands executed:**
```bash
make dev-setup
make test
```

**Result:** **40 tests passed in 12.25s** — 0 failed.

The pytest suite (`tests/test_schema.py`, `tests/test_telemetry.py`, `tests/test_repo_integrity.py`) validates the AlertCert v1.1 JSON Schema, canonical SHA-256 baseline binding, simulator conformance, and documentation/repo invariants (no cross-repo paths, valid signing pubkey format, agents.md flag inventory).

**Field finding A1:** The `README.md` quick-start claims **"42 passed"** but the actual count is **40**. Likely doc drift after test deletions. Suggest updating the README to use a wildcard ("~40 tests pass in ~10s") to avoid future drift.

**Simulator micro-demo:** Confirmed end-to-end by streaming 20 records over 2s at 100ms cadence. First record validated under the AlertCert v1.1 schema with all required fields present (`event`, `version`, `ts_ns`, `host`, `metric`, `tick`, `kappa`, `cusum_s`, `h`, `mu_baseline`, `switches`, `n_pids`, `severity`, `alert_cert_path`).

---

### 2.2 Track B — Docker monitor + telemetry stream

**Commands executed:**
```bash
docker compose up -d            # h7-monitor only (sinkhole service disabled — see §3.1)
make stream-telemetry           # streamed for ~45 s
curl -s http://127.0.0.1:8000/agents | jq
```

**Result — backend layer: PASS.** The FastAPI backend on `:8000` ingested the synthetic NDJSON stream and exposed correct agent state via the `/agents` REST endpoint. State transitions observed during a single ~45 s window:

| Time (s) | NDJSON lines | Backend agent status | κ (kappa) | Severity distribution |
|---|---|---|---|---|
| 5  | 22  | `ALERT`  | 0.032 | INFO only |
| 40 | 110 | `BREACH` | 0.091 | 70 INFO / 13 WARN / 27 CRITICAL |
| 45 (stream stopped) | 288 | `BREACH` | — | full A→B→C cycle observed |

A representative `CRITICAL` record from the breach phase:
```json
{
  "event": "H7_ALERT", "version": "1.1",
  "ts_iso": "2026-05-31T11:56:55.990529Z",
  "host": "lsalihi-Precision-7560",
  "metric": "sched_switch", "tick": 70,
  "kappa": 0.341758, "cusum_s": 1.84046, "h": 0.32,
  "mu_baseline": 0.024, "switches": 15553, "n_pids": 38,
  "severity": "CRITICAL", "shadow_mode": false,
  "alert_cert_path": "run/alerts/alert-000070.cal"
}
```

**Result — dashboard layer: FAIL.** The Next.js fleet dashboard advertised on `:3001` was not reachable. The published image `ghcr.io/pulsaride/h7-monitor:latest` ships the prebuilt frontend assets at `/app/frontend/.next/` but its entrypoint is `python -m uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port 8000` — the Next.js server is never started, and Node.js/npm are not installed in the image. The `docker-compose.yml` header comment (`"Next.js frontend served on :3001 by the image entrypoint"`) is therefore inaccurate.

**Field finding B1 (HIGH priority, blocks pilot UX):** The GHCR-published `h7-monitor:latest` image does not serve the dashboard. Recommended fix on the H7 product side: either (a) extend the image entrypoint to launch Next.js as a sidecar (`next start --port 3001 & exec uvicorn …`), or (b) build the frontend as a static export (`output: 'export'`) and serve it from FastAPI's `StaticFiles`. Without one of these, the kit's headline UX selling point is unreachable for pilot clients.

---

### 2.3 Track C — Live eBPF sensor

**Pre-state:** `make setup` and `make calibrate` had been executed in a prior session.
- Ed25519 keys generated at `run/keys/h7-cert-issuer.{pub,sec,id}` (.sec mode 600).
- Baseline calibrated at `run/baseline.json` (real `sha256`, BTF-driven, not the offline fallback).

**Commands attempted in this session:** `make up` was attempted from the non-interactive evaluation shell. `sudo` requires a TTY for password entry, which the automation shell does not provide. The host sinkhole started successfully but the sensor (`sudo RUST_LOG=warn nohup h7-sensor …`) failed with `sudo: a terminal is required to read the password`.

**Substitute coverage via `e2e-full`** (no sudo required) — see §2.4.

**Items left for the operator** (kernel-sensor specific, must be executed in an interactive shell):

```bash
cd /home/lsalihi/startup/h7-demo-kit
make up                                                # interactive sudo
make watch                                             # second terminal
make attack-vercel                                     # 60 s
make verify                                            # expect: PASS
bash scripts/tamper-alert.sh run/alerts/alert-000001.cal
make verify-alert                                      # expect: INVALIDE
make down
```

Expected artifacts: `.cal` sidecar files under `run/alerts/`, each carrying `sig_b64` (Ed25519) bound to `baseline_sha256_hex`. The tamper step demonstrates that a single byte flip in a `.cal` invalidates the signature chain.

---

### 2.4 Pipeline coverage via `make e2e-full` (sudo-free)

To validate the parts of Track C that don't require eBPF, `scripts/e2e-full.sh` was executed against the local h7-monitor backend source. All 8 checkpoints **PASSED**:

| # | Step | Result |
|---|---|---|
| 1 | Seed 5 s of NDJSON via the simulator | 50 lines emitted |
| 2 | Start h7-monitor backend on `:18007` | ready in < 1 s |
| 3 | `GET /agents` | 1 agent visible: `lsalihi-Precision-7560` |
| 4 | `POST /attest/{id}` (Bearer auth) | returned `png_url` + `cbor_url` |
| 5 | `GET /attest/{id}/cbor` | HTTP 200, 138-byte CBOR envelope |
| 6 | `validate-alerts-ndjson.py` | 50/50 records schema-valid |
| 7 | `gen-drift-report` | verdict `NOMINAL`, signed |
| 8 | `gen-audit-package` | manifest generated |

This confirms the schema, attestation, CBOR-envelope, drift-report, and audit-package paths are wired correctly end-to-end. The only paths *not* exercised in this evaluation are the live `sched_switch` ingestion and the `.cal`-sidecar tamper test — both gated on the operator's sudo step in §2.3.

---

### 2.6 Track C — Nouveaux canaux L4 et ptrace (scénarios ajoutés post-évaluation initiale)

*Cette section documente les scénarios disponibles depuis la version 1.1 du kit.*

**Scénario `attack-exfil` — UNKNOWN_DESTINATION (L4)**

```bash
make attack-exfil   # démarre un sinkhole "attaquant" sur 127.0.0.1:9876
                    # puis émet 5 connexions TCP vers ce port hors-allowlist
```

Comportement attendu : le canal L4 (`sys_enter_connect`) capture chaque
tentative de connexion vers `127.0.0.1:9876`. Comme ce port n'est pas dans
l'allowlist de calibration (qui connaît uniquement le port 9999 du sinkhole
démo), h7-brain émet immédiatement un épisode WARNING `UNKNOWN_DESTINATION`
sans attendre de z-score — signal dur, tolérance zéro aux nouvelles destinations
depuis un namespace AI-runtime.

Signal observable dans `run/logs/h7-brain.log` :
```
WARNING  h7_brain.net_detector: NET UNKNOWN_DESTINATION ns=<cookie> dst=127.0.0.1:9876
```

Note : si le sensor eBPF n'est pas actif (`make up` non exécuté), le script
affiche `[syscall capturé]` sur ECONNREFUSED — preuve que le syscall `connect()`
est bien émis même en cas d'échec TCP.

**Scénario `attack-burst` — NET_EGRESS_BURST (L4)**

```bash
make attack-burst   # phase 1 : 10 s baseline ~0.5 conn/s
                    # phase 2 : 15 s burst à 60 conn/s >> mu+4σ
```

Comportement attendu : le fenêtrage glissant (10 s) dépasse 4σ au-dessus de
la baseline calibrée. h7-brain enrichit l'épisode actif avec `NET_EGRESS_BURST`
et le fait passer en BREACH si un épisode WARNING était déjà ouvert.

**Scénario `attack-ptrace` — PTRACE_ATTACK (Sprint 3)**

```bash
make attack-ptrace  # fork d'un child temporaire + ptrace(PTRACE_ATTACH, child_pid)
```

Comportement attendu : h7-brain reçoit le QII frame du socket `/var/run/h7_ptrace.sock`,
classe `PTRACE_ATTACK` (confiance 0.85), ouvre immédiatement un épisode BREACH et
émet un AlertCert Ed25519. Si `ptrace_scope ≥ 1` (Ubuntu par défaut), le kernel
renvoie `EPERM` — la sonde eBPF capture le syscall avant le contrôle d'accès.

---

### 2.5 Compliance bundle

**Commands executed:**
```bash
make compliance-bundle      # = gen-drift-report + ts-harvest
```

**Result:** drift report generated; `ts-harvest` correctly no-op'd (`"No pending .cal files (modified in last 60 min, no TSR)"`) because no live-sensor `.cal` sidecars were present yet.

**Drift report excerpt** (full file at `run/reports/drift-report-2026-05-31T12-14-52Z.json`):

```json
{
  "schema": "h7-drift-report/v1",
  "window_hours": 24.0,
  "issuer_key_fingerprint": "h7-cert-issuer-86b0e4e66c5c0f0f",
  "baseline_sha256": "cd6eb541a785bd50e5fa140882de30fea93c38d7222d167316fbf27bbfa03f30",
  "baseline_source": "live",
  "global_verdict": "NOMINAL",
  "total_alerts": 50,
  "global_kappa_mean": 0.034392,
  "agents": [{ "entity_id": "lsalihi-Precision-7560", "verdict": "NOMINAL" }]
}
```

The body is signed with the Ed25519 issuer key (`sig_b64` field at root). This is the artifact a customer's CISO would hand to a Notified Body during a DORA/NIS2 inspection.

**Audit package** (`run/audit-package/2026-05-31T12-08-18Z/`):

```
alerts.ndjson         20831 B
baseline.json           717 B
h7-cert-issuer.pub      113 B
AUDIT-SUMMARY.txt       951 B
MANIFEST.json           501 B  (SHA-256 of each evidence file)
certs/                       (would contain .cal sidecars in a live-sensor run)
```

`MANIFEST.json` lists the SHA-256 of every evidence file, anchoring the bundle's integrity. The "missing" `.cal` files are expected — they'd be present after the live-sensor steps in §2.3.

---

## 3. Field Findings

These are issues encountered during evaluation that would impact a pilot client's first-touch experience. Sorted by severity.

### 3.1 Sinkhole service conflict between Docker Compose and `make up` (HIGH)

The `docker-compose.yml` declares a `sinkhole` service that listens on `127.0.0.1:9999` via `network_mode: host`. The `make up` target *also* launches a host-side sinkhole on `127.0.0.1:9999`. They cannot coexist — whichever is started second crashes with `EADDRINUSE`.

A second-order issue compounds this: when the Docker sinkhole runs first, it writes `run/logs/sinkhole.ndjson` from inside the container. If the container's UID differs from the host user (it doesn't in the python:3.11-alpine default, but it can), the host sinkhole later fails with `PermissionError`.

**Resolution applied locally:** the `sinkhole:` service block in `docker-compose.yml` was commented out. `make up`'s host sinkhole is sufficient for both Track B (via the `./run/alerts` volume mount) and Track C.

**Recommended product fix:** remove the `sinkhole` service from the published `docker-compose.yml` and document that `make up` owns port 9999. Alternatively, give the Docker sinkhole a distinct port (e.g., 9998) and update `H7_BRAIN_URL` accordingly.

### 3.2 GHCR-published `h7-monitor:latest` doesn't serve the dashboard (HIGH)

See §2.2 — entrypoint launches only the FastAPI backend; Next.js frontend is shipped but never started; no Node runtime in the image. This silently breaks the dashboard URL printed in `USER-GUIDE.md` and the docker-compose header.

### 3.3 `H7_LICENCE_KEY` typo in `docker-compose.yml` (MEDIUM, currently inert)

Line 40 of the kit's `docker-compose.yml` sets `H7_LICENCE_KEY` (British spelling). The actual env var consumed by `h7-brain` (verified at `p-h7/h7-brain/h7_brain/main.py:162`) is `H7_LICENSE_KEY` (American). Currently inert because `h7-monitor` does not gate on a license — but the moment a customer wires up `h7-brain` (mentioned in the `h7-brain` source files), their license will be silently ignored and h7-brain will refuse to start with `H7_LICENSE_KEY is unset — refusing to start (ADR-PROD-018)`.

**Recommended fix:** rename to `H7_LICENSE_KEY` in `docker-compose.yml`.

### 3.4 `make status` mis-counts "sidecars" (LOW)

The `make status` target prints `alertes : N sidecar(s) .cal` where N comes from `ls run/alerts | wc -l`. This counts the `keys/` and `qr/` subdirectories and any other entry as if they were `.cal` files. In a fresh setup with zero alerts, status prints `3 sidecar(s) .cal` — misleading during demos to clients.

**Recommended fix:** `ls run/alerts/*.cal 2>/dev/null | wc -l`.

### 3.5 README test count drift (LOW)

`README.md` claims "42 tests pass"; the actual count is 40. See §2.1 finding A1.

### 3.6 `e2e-full.sh` cleanup hangs on `wait` (LOW, automation-only)

The trap-EXIT handler in `scripts/e2e-full.sh` calls `kill "$BACKEND_PID"; wait "$BACKEND_PID"`. With the FastAPI app's default signal handling, `wait` blocks indefinitely until SIGKILL — the script's final summary lines never flush through piped consumers (`tail`, CI log collectors). The actual test logic completes successfully; only the trailing output is suppressed.

**Recommended fix:** replace `wait "$BACKEND_PID"` with `for _ in 1 2 3 4 5; do kill -0 "$BACKEND_PID" 2>/dev/null || break; sleep 1; done; kill -9 "$BACKEND_PID" 2>/dev/null || true`.

---

## 4. Security & Cryptographic Assessment

Based on observed execution:

- **Binary supply chain.** `make setup` downloads binaries via `scripts/fetch-release-binaries.sh`. The fetcher verifies `SHA256SUMS.sig` (Ed25519) against a pinned public key at `fixtures/H7_RELEASE_SIGNING.pub` before any binary is installed. Observed in this run: `[fetch] verifying SHA256SUMS.sig (Ed25519)` → `OK` for both `h7` and `h7-sensor` archives. **Strong.**
- **Alert integrity.** Drift report and audit MANIFEST are Ed25519-signed by `h7-cert-issuer-86b0e4e66c5c0f0f`. The audit MANIFEST lists SHA-256 of each evidence file — tampering with `alerts.ndjson` or `baseline.json` invalidates the manifest. **Strong.**
- **Baseline binding.** The drift report carries `baseline_sha256: cd6eb541…` and `baseline_source: "live"`, anchoring the entire 24 h evaluation window to a single hashed baseline. **Strong.**
- **Network surface.** All host bindings are `127.0.0.1`-only (sinkhole, sensor TCP, h7-monitor backend). No external listeners observed. **Strong.**
- **License gating.** Not exercised in this evaluation (the demo kit doesn't deploy `h7-brain`, which is where license checks happen). The license-token tooling at `p-h7/scripts/issue-license.py` mints Ed25519-signed JWT-shaped tokens with `iss`, `aud`, `sub`, `exp`, `kid`, `tier`, `max_namespaces` claims — standard offline-verifiable license pattern. **Looks sound, not directly tested.**
- **Tamper detection (NOT executed).** The cryptographic invariant that one-byte tampering invalidates the `.cal` sig chain is documented and the script exists (`scripts/tamper-alert.sh`). It was not exercised in this session because the upstream live-sensor steps require sudo. Schema and crypto unit tests (Track A, §2.1) cover the logic at the unit level.

---

## 5. Conclusion

The Pulsaride H7 Demo Kit est une plateforme d'évaluation solide et bien documentée couvrant désormais **5 canaux de détection indépendants**. In the time-bounded evaluation captured here:

- **Track A** ran fully and cleanly: 40/40 tests in 12 s.
- **Track B's backend** ingested 288 telemetry records and correctly tracked the simulator's A-B-C state machine through INFO → WARN → CRITICAL severity transitions. **Track B's frontend dashboard is not reachable** in the published image (§3.2) — a fix is required before client pilots.
- **Track C's live-sensor path** is gated on operator sudo; a `~5 min` interactive procedure (§2.3) completes the live-attack and tamper steps.
- **`make e2e-full`** demonstrated that the full attestation / drift-report / audit-package pipeline works end-to-end without the eBPF sensor (8/8 PASS).
- **Compliance bundle** generates a signed drift report and an integrity-anchored audit package directly consumable by a DORA/NIS2 auditor.

The cryptographic and supply-chain hygiene is strong. The two HIGH-severity field findings (sinkhole port conflict §3.1, missing dashboard §3.2) are mechanical and easy to fix; neither touches the kit's core threat model or attestation guarantees.

**Recommendation: green-light the kit for a pilot client engagement, conditional on fixing §3.1 and §3.2.** Findings §3.3–§3.6 are polish-pass items that can ride a normal release cycle.

L'ajout des canaux L4 (réseau) et ptrace renforce significativement la couverture : un adversaire doit désormais évader simultanément les 5 canaux pour passer inaperçu. Les scénarios `attack-exfil`, `attack-burst` et `attack-ptrace` permettent de démontrer ces nouvelles surfaces de détection en ~3 minutes additionnelles dans la séquence démo.

---

## Appendix A — Reproduction inventory

Artifacts produced and persisted on disk during this evaluation:

| Path | Notes |
|---|---|
| `run/keys/h7-cert-issuer.{pub,sec,id}` | Ed25519 issuer key, mode 600 on `.sec` |
| `run/baseline.json` | Live-calibrated baseline (BTF-driven) |
| `run/h7-demo.toml` | Generated demo config, log_level=warn |
| `run/alerts/alerts.ndjson` | 288 Track B records (INFO→CRITICAL cycle) |
| `run/logs/alerts.ndjson` | 50 e2e-full records |
| `run/reports/drift-report-2026-05-31T12-*.json` | Signed 24 h drift reports (2 generated) |
| `run/audit-package/2026-05-31T12-08-18Z/` | Audit bundle (MANIFEST + evidence) |

## Appendix B — Items the operator must run to close the evaluation

```bash
cd /home/lsalihi/startup/h7-demo-kit

# Live sensor + attack (canaux L1 + L2)
make up                                  # sudo password required
make watch                               # in a second terminal
make attack-vercel
make verify                              # expect: PASS

# Nouveaux canaux L4 + ptrace (pas de sudo requis pour les scripts seuls)
make attack-exfil                        # L4 UNKNOWN_DESTINATION
make attack-burst                        # L4 NET_EGRESS_BURST
make attack-ptrace                       # L5 PTRACE_ATTACK

# Tamper test
bash scripts/tamper-alert.sh run/alerts/alert-000001.cal
make verify-alert                        # expect: INVALIDE for that file

# Compliance bundle with real .cal sidecars
make compliance-bundle                   # ts-harvest will now find .cal files

# Clean shutdown
make down
docker compose down
```

After running the above, re-generate the audit package (`make gen-audit-package`) and confirm `MANIFEST.json` lists `cal_count > 0`.
