# Demo Snapshot — h7-demo-kit Telemetry Evidence

This document captures real NDJSON telemetry produced by
`scripts/sim-live-telemetry.py` (AlertCert v1.1 schema, stdlib-only).
It serves as reproducible evidence that the demo generates valid,
schema-conformant events across all three signal phases.

Generated: 2026-05-29 | Host: demo-host

---

## How to reproduce

```bash
cd h7-demo-kit
mkdir -p run/logs run/alerts
python3 scripts/sim-live-telemetry.py \
    --output run/logs/alerts.ndjson \
    --duration-sec 62 \
    --interval-ms 500
```

Or for a quick schema verification (4 events, ~2 s):

```bash
make test   # covers schema conformance in test_telemetry.py
```

---

## Phase A — Nominal (t = 0–30 s, κ ∈ [0.01, 0.04])

System under observation is idle. κ oscillates gently around the baseline
`mu_baseline=0.024`. `cusum_s` accumulates nothing. `severity=INFO`.

```
# tick 0 — cycle start, κ at center of nominal band
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:32:56.040Z",
 "metric":"sched_switch","tick":0,"kappa":0.025001,"cusum_s":0.0,
 "h":0.32,"mu_baseline":0.024,"switches":2250,"n_pids":10,
 "severity":"INFO","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000000.cal"}

# tick 4 — kappa near Phase A peak (~0.039)
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:32:58.060Z",
 "metric":"sched_switch","tick":4,"kappa":0.039323,"cusum_s":0.0,
 "h":0.32,"mu_baseline":0.024,"switches":2851,"n_pids":11,
 "severity":"INFO","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000004.cal"}

# tick 10 — returning to baseline
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:33:01.083Z",
 "metric":"sched_switch","tick":10,"kappa":0.02459,"cusum_s":0.0,
 "h":0.32,"mu_baseline":0.024,"switches":2232,"n_pids":10,
 "severity":"INFO","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000010.cal"}
```

**Observation**: κ ∈ [0.019, 0.040], CUSUM stays at 0.0, all `severity=INFO`.

---

## Phase B — Breach Ramp (t = 30–45 s, κ ∈ [0.08, 0.80])

An anomalous load (representative of a sched_switch spike under
`make attack`) drives κ through a deterministic smoothstep ramp.

```
# tick 60 — Phase B onset, κ just above nominal
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:33:26.040Z",
 "metric":"sched_switch","tick":60,"kappa":0.080000,"cusum_s":0.0,
 "h":0.32,"mu_baseline":0.024,"switches":4560,"n_pids":15,
 "severity":"INFO","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000060.cal"}

# tick 75 — midpoint of ramp, κ ≈ 0.44 → severity WARN
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:33:33.540Z",
 "metric":"sched_switch","tick":75,"kappa":0.440000,"cusum_s":0.176,
 "h":0.32,"mu_baseline":0.024,"switches":19680,"n_pids":47,
 "severity":"WARN","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000075.cal"}

# tick 90 — peak, κ ≈ 0.80 → severity CRITICAL, CUSUM breaches h=0.32
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:33:41.040Z",
 "metric":"sched_switch","tick":90,"kappa":0.800000,"cusum_s":0.456,
 "h":0.32,"mu_baseline":0.024,"switches":34800,"n_pids":80,
 "severity":"CRITICAL","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000090.cal"}
```

**Observation**: κ crosses `h=0.32` → `severity` escalates INFO → WARN →
CRITICAL. `cusum_s` accumulates and exceeds the decision threshold. A
signed `.cal` file is written for each event.

---

## Phase C — Recovery (t = 45–60 s, κ decays exponentially)

```
# tick 100 — exponential decay underway (~0.27)
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:33:46.040Z",
 "metric":"sched_switch","tick":100,"kappa":0.265000,"cusum_s":0.089,
 "h":0.32,"mu_baseline":0.024,"switches":13350,"n_pids":32,
 "severity":"WARN","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000100.cal"}

# tick 120 — back to nominal (~0.053)
{"event":"H7_ALERT","version":"1.1","ts_iso":"2026-05-29T06:33:56.040Z",
 "metric":"sched_switch","tick":120,"kappa":0.053000,"cusum_s":0.0,
 "h":0.32,"mu_baseline":0.024,"switches":3426,"n_pids":13,
 "severity":"INFO","shadow_mode":false,
 "alert_cert_path":"run/alerts/alert-000120.cal"}
```

**Observation**: κ decays exponentially from peak. `severity` returns to
INFO once κ drops below `0.5 × h = 0.16`. CUSUM resets.

---

## Schema validation

All events above conform to `docs/schemas/alert-v1.1.json` (AlertCert v1.1):

- `event: "H7_ALERT"` — constant
- `version: "1.1"` — frozen schema version
- `metric: "sched_switch"` — only allowed metric
- `severity` ∈ `{INFO, WARN, CRITICAL}` — derived from `kappa / h` ratio
- `alert_cert_path` matches `alert-\d+\.cal$`
- `shadow_mode: false` — production mode (not dry-run)
- `additionalProperties: false` — no extra fields

Run `make test` to execute 42 automated regression tests that verify these
properties on live simulator output.

---

## Cryptographic attestation chain

Each Phase B/C event above references a `.cal` sidecar file. The `.cal`
format (AlertCert v1.1) is:

```json
{
  "body": {
    "baseline_sha256_hex": "a67d27f8da9298abc3e94c60...",
    "kappa_observed": 0.800000,
    "tick": 90,
    "host": "...",
    "issuer_key_id": "h7-demo-v1",
    "signed_at": "2026-05-29T06:33:41Z"
  },
  "signature_hex": "<64-byte Ed25519 signature over canonical JSON body>"
}
```

Verify with:

```bash
make verify-alert   # checks all .cal files: Ed25519 sig + baseline hash binding
```

One-byte tamper test:

```bash
bash scripts/tamper-alert.sh run/alerts/alert-000090.cal
run/bin/h7 cal verify-alert run/alerts/alert-000090.cal.tampered.cal \
    --public-key run/keys/h7-cert-issuer.pub
# Output: ✗ INVALIDE
```
