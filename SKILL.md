---
name: h7-demo-kit
description: Operate, validate, and harden the Pulsaride-H7 Behavioral Cryptographic Attestation (BCA) demo kit. Use for setup, calibration with BTF fallback, live-telemetry simulation, attack drills, alert signature verification, gateway regression tests, and signed release fetching.
license: See LICENSE
---

# H7 Demo Kit — Operator & Security Tester Skill

Structured workflow to provision, exercise, and regression-test the Pulsaride-H7
BCA demo kit. The kit observes `sched_switch` via eBPF, emits Ed25519-signed
`.cal` attestations, and streams `H7_ALERT v1.1` NDJSON to a monitor UI.

## When to use this skill

- Bringing up the kit on a fresh Linux host (with or without BTF).
- Running attack drills and verifying the alert pipeline (`.cal` signatures, schema, baseline).
- Sealing the monitor gateway against `/qr` path traversal and `/stream` trace leaks.
- Fetching and verifying signed release binaries with a pinned local public key.

Do **not** use this skill for: editing monitor backend/frontend code (separate
repository), or modifying the `AlertCert v1.1` schema (frozen contract).

## Workflow

### 1. Map the product surface

- Sensor: eBPF probe on `sched_switch`, computes `kappa` and CUSUM `S`.
- Output: NDJSON stream at `run/logs/alerts.ndjson` + per-event `.cal` sidecars in `run/alerts/`.
- Trust root: Ed25519 release-signing key pinned at `fixtures/H7_RELEASE_SIGNING.pub`.

### 2. Audit the local environment

Required: `docker`, `docker compose`, `make`, `python3` (>= 3.10), `openssl`.

```bash
make check     # prints dependency and host status
```

BTF presence determines the calibration path:

```bash
test -r /sys/kernel/btf/vmlinux && echo "BTF available" || echo "BTF missing -> offline fallback"
```

### 3. Fetch signed binaries (fail-closed)

```bash
make fetch-binaries
```

The script `scripts/fetch-release-binaries.sh` refuses to proceed unless the
pinned local public key is present. Override only with a trusted local file:

```bash
H7_RELEASE_SIGNING_PUBKEY_FILE=/abs/path/to/H7_RELEASE_SIGNING.pub make fetch-binaries
```

Never fetch keys from the network.

### 4. Calibrate (with built-in BTF fallback)

```bash
make calibrate
```

Behavior:

- If `run/baseline.json` already has a non-`pending` `sha256`, calibration is skipped.
- Else if `/sys/kernel/btf/vmlinux` is **absent**, the target diverts automatically
  to `make seed-offline-baseline`, which runs:
  ```bash
  python3 scripts/seed-offline-baseline.py \
      --fixture fixtures/baseline.example.json \
      --output  run/baseline.json
  ```
  This computes a deterministic SHA-256 over the canonical fixture body, writes
  it self-referentially, and stamps `calibration_source: offline-fallback` plus
  `btf_available: false`. No network is touched.
- Else the sensor performs a ~2 min live calibration (`sudo` required).

After calibration, `make up` will accept the baseline (the `pending` guard is cleared).

### 5. Bring the stack up

```bash
make up           # start docker compose stack
make status       # confirm services are healthy
```

### 6. Drive live telemetry into the UI (optional)

For UI work without the kernel sensor, run the deterministic simulator:

```bash
make stream-test-telemetry
# = python3 scripts/sim-live-telemetry.py
```

Three-phase signal (60 s default): Phase A nominal (`kappa` 0.01–0.04),
Phase B breach (peaks 0.65–0.85 past the CUSUM threshold), Phase C decay back
to baseline. Output is appended to `run/logs/alerts.ndjson`, schema-validated
against `docs/schemas/alert-v1.1.json`.

### 7. Functional validation

```bash
make attack             # local drift drill
make attack-vercel      # isolated vercel-pattern fork burst
make verify-baseline    # baseline integrity
make verify-alert       # .cal signature + payload integrity
make verify-schema      # NDJSON against AlertCert v1.1
make verify             # = verify-alert + verify-schema
make test-btf-fallback          # regression: offline-fallback produces valid baseline (no BTF)
make test-kernel-heterogeneous  # regression: BTF-absent + BTF-present + pending guard
```

For ad-hoc proofs:

```bash
python3 scripts/validate-alerts-ndjson.py run/logs/alerts.ndjson
```

### 8. Defensive regression suite (gateway hardening)

Asserts that the h7-monitor FastAPI gateway rejects path traversal on
`GET /qr/{filename}` and conceals stack traces on the `/stream` WebSocket.

```bash
# Default: looks for the monitor backend at ../../h7-monitor/backend
make verify-gate-hardening

# Or point to an arbitrary checkout
H7_MONITOR_BACKEND_DIR=/abs/path/to/h7-monitor/backend \
    make verify-gate-hardening
```

Requires `fastapi[testclient]` and `httpx` in the Python environment. Exits
non-zero on the first regression.

Manual smoke checks against a running monitor (default port 8000):

```bash
curl -i 'http://localhost:8000/qr/..%2F..%2Fetc%2Fpasswd.png'   # expect 4xx
curl -i 'http://localhost:8000/qr//etc/passwd'                  # expect 4xx
curl -i 'http://localhost:8000/qr/sub/dir.png'                  # expect 4xx
```

### 9. Demo live — métriques de succès

A demo run is considered successful when **all** of the following hold:

| Metric | Target | How to measure |
|---|---|---|
| **API latency** `GET /agents` | p95 < 200 ms | `curl -w "%{time_total}" http://localhost:8000/agents` (3 runs) |
| **WebSocket stability** `/stream` | No disconnect during 60 s Phase A–C cycle | `sim-live-telemetry.py --duration-sec 60`; monitor UI shows no reconnect banner |
| **κ drift visibility** | Phase B breach (κ > 0.32) appears in UI within 2 ticks (≤ 1 s at 500 ms interval) | Inspect sparkline on the agent card during Phase B (t=30–45 s) |
| **Alert count coherence** | `alert_count` in `/agents` matches line count in `alerts.ndjson` | `python3 scripts/validate-alerts-ndjson.py run/logs/alerts.ndjson` exit 0 |
| **Gate hardening** | `verify-gate-hardening.py` exits 0 | `make verify-gate-hardening` |
| **QR attestation round-trip** | `POST /attest/{id}` returns valid PNG URL, HTML viewer renders | `curl -H "Authorization: Bearer $H7_ATTEST_TOKEN" -X POST http://localhost:8000/attest/<id>` |

Fail-gate: if any metric above misses, stop the demo and diagnose before re-attempting.

### 10. Paquet de preuves audit client

Génère un bundle autonome (MANIFEST.json + alertes + `.cal` + baseline + résumé) :

```bash
make gen-audit-package
# → run/audit-package/YYYY-MM-DDTHH-MM-SSZ/
#     MANIFEST.json          (SHA-256 de chaque fichier)
#     alerts.ndjson
#     baseline.json
#     certs/alert-*.cal
#     AUDIT-SUMMARY.txt
#     h7-cert-issuer.pub
```

Le paquet est autonome et vérifiable hors-ligne (`h7 cal verify`).

### 12. Tear down / reset

```bash
make reset-alerts   # clear NDJSON + .cal artefacts
make down           # stop stack
make clean          # full cleanup
```

## Guardrails

- **Fail-closed**: any signature, schema, or pinned-key check that fails must abort the run; never substitute network-fetched assets.
- **Schema frozen**: do not mutate `AlertCert v1.1` or the `.cal` envelope.
- **No sudo escalation in CI**: skip `make calibrate` (live mode) in unprivileged environments and rely on the offline fallback.
- **Monitor lives in its own repository**: never copy backend/frontend code into this kit.

## Troubleshooting cheatsheet

| Symptom | Action |
|---|---|
| `make up` refuses with `sha256: pending` | Run `make calibrate` (auto-fallback handles missing BTF). |
| `os error 22` / `BPF_PROG_LOAD` failure | Confirm BTF missing; rerun `make calibrate` so the BTF guard diverts to `seed-offline-baseline`. |
| `fetch-binaries` aborts with `REFUS` | Restore `fixtures/H7_RELEASE_SIGNING.pub` or set `H7_RELEASE_SIGNING_PUBKEY_FILE` to a trusted local path. |
| `verify-gate-hardening` cannot import `main:app` | Set `H7_MONITOR_BACKEND_DIR` to the absolute path of the monitor `backend/` directory. |
| Simulator writes nothing | Ensure `run/logs/` exists or pass `--output` to `sim-live-telemetry.py`. |
