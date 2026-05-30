# User Guide — Pulsaride-H7 Demo Kit

Hands-on guide for evaluators, security engineers, and compliance auditors.
**This kit is fully self-contained**: no other repository, no cloud account,
no internet beyond first `make setup` is required.

If you only have 2 minutes, read [Part 1](#part-1--two-minute-track-a).
If you have 20 minutes and a Linux machine, read all the way through.

---

## Table of contents

1. [Two-minute Track A — schema + crypto validation](#part-1--two-minute-track-a)
2. [Five-minute Track B — Docker monitor stack](#part-2--five-minute-track-b)
3. [Fifteen-minute Track C — live eBPF sensor demo](#part-3--fifteen-minute-track-c)
4. [Tamper-detection demo](#part-4--tamper-detection-demo)
5. [Compliance evidence packages](#part-5--compliance-evidence-packages)
6. [Offline / air-gap operation](#part-6--offline--air-gap-operation)
7. [Running the test suite](#part-7--running-the-test-suite)
8. [Troubleshooting](#part-8--troubleshooting)
9. [Key files reference](#part-9--key-files-reference)

---

## Part 1 — Two-minute Track A

Goal: validate the schema, the canonical hash algorithm, and the telemetry
simulator without any kernel, sudo, or Docker.

```bash
git clone https://github.com/pulsaride/h7-demo-kit
cd h7-demo-kit
make dev-setup                # creates venv/ + installs pytest
make test                     # 42 tests, ~12 seconds
```

Expected output:

```
============================= 42 passed in 12.34s ==============================
```

Generate a sample telemetry stream and inspect it:

```bash
mkdir -p run/logs run/alerts
python3 scripts/sim-live-telemetry.py \
    --output run/logs/alerts.ndjson \
    --duration-sec 10 \
    --interval-ms 500

head -2 run/logs/alerts.ndjson | python3 -m json.tool
```

You will see two events conforming to AlertCert v1.1, with `event:H7_ALERT`,
`version:1.1`, a `kappa` in the nominal range, and a `severity` of INFO.

Validate them against the frozen schema:

```bash
python3 scripts/validate-alerts-ndjson.py run/logs/alerts.ndjson
```

---

## Part 2 — Five-minute Track B

Goal: bring up the live fleet dashboard from the public GHCR container
image, feed it real telemetry, and download a CBOR attestation envelope.

### Prerequisites

| Component | Minimum | Check |
|---|---|---|
| Docker Engine | 20+ | `docker info` |
| Docker Compose v2 | bundled with Docker | `docker compose version` |

### Steps

```bash
# 1. Pull h7-monitor (public GHCR image) and start the sinkhole
docker compose up -d
docker compose ps              # both services should be Up

# 2. Stream NDJSON telemetry to the path the container reads
make stream-telemetry          # writes run/alerts/alerts.ndjson

# Leave this running. Switch to a second terminal for the next step.
```

In a second terminal:

```bash
# 3. Watch live agents appear in h7-monitor
curl -s http://127.0.0.1:8000/agents | jq '.[0]'

# 4. Open the Next.js fleet UI
xdg-open http://127.0.0.1:3001 || open http://127.0.0.1:3001
```

The dashboard shows κ, CUSUM, and severity in real time. Toward the end
of each 60-second cycle, you will see the agent transition INFO → WARN →
CRITICAL → INFO as the simulator runs through Phases A, B, C.

### Stop

```bash
# Ctrl-C the stream-telemetry process in the first terminal
docker compose down -v
```

---

## Part 3 — Fifteen-minute Track C

Goal: run the real eBPF sensor against your own kernel, generate a
genuine `sched_switch` breach, and verify the Ed25519 attestation chain.

### Prerequisites

| Component | Minimum | Check |
|---|---|---|
| Linux kernel | 5.8+ | `uname -r` |
| eBPF + BTF | `/sys/kernel/btf/vmlinux` present (auto-fallback if absent) | `ls /sys/kernel/btf/vmlinux` |
| `sudo` | for sensor mode (CAP_BPF + CAP_SYS_ADMIN) | `sudo -v` |
| `openssl`, `curl`, `jq` | `make check` enforces | `make check` |

### Step 1 — Fetch signed binaries

```bash
make setup                    # internally calls fetch-release-binaries.sh
```

This downloads `h7` (verify CLI) and `h7-sensor` (eBPF sensor) from the
public `pulsaride/h7-demo-kit` GitHub Releases. **The Ed25519 signature
on `SHA256SUMS.sig` is verified against the pinned key
`fixtures/H7_RELEASE_SIGNING.pub`**. There is no fallback to a
network-fetched key — if the pinned key is missing or the signature
mismatches, the fetch refuses to install.

Ephemeral demo signing keys for the Issuer are also generated into
`run/keys/` at this step.

### Step 2 — Calibrate a baseline

```bash
make calibrate                # ~2 min, sudo if BTF is present
```

- **BTF present**: live calibration of the κ/CUSUM thresholds against
  your machine's idle profile (~2 min, requires sudo).
- **BTF absent**: automatic fallback to the pinned offline fixture
  (instant, no sudo).

### Step 3 — Start the sensor + sinkhole

```bash
make up                       # sensor in monitor mode, sinkhole on 127.0.0.1:9999
```

In a second terminal:

```bash
make watch                    # tail -F run/logs/alerts.ndjson
```

You will see baseline `kappa ≈ 0.02` events scrolling at ~10 lines/s.

### Step 4 — Trigger an alert

```bash
make attack                   # 60 s, 4 workers, generic sched_switch load
# OR
make attack-vercel            # 60 s, supply-chain pattern (2026-04-21 reconstitution)
```

Within ~5 s of `make attack` you will see `severity` transition to `WARN`
then `CRITICAL`. An Ed25519-signed `.cal` file is written to `run/alerts/`
for each transition.

### Step 5 — Verify

```bash
make verify                   # all .cal: Ed25519 sig + baseline_sha256_hex binding + schema
```

Expected:

```
✓ alert-000001.cal  (Ed25519 OK, baseline binding OK)
```

### Step 6 — Teardown

```bash
make down                     # stops sensor + sinkhole, purges raw logs (keeps .cal)
```

---

## Part 4 — Tamper-detection demo

This is the showcase moment for compliance audiences: a single modified
byte invalidates the Ed25519 signature.

```bash
# After running Track C steps 1–5:
bash scripts/tamper-alert.sh run/alerts/alert-000001.cal

run/bin/h7 cal verify-alert run/alerts/alert-000001.cal.tampered.cal \
    --public-key run/keys/h7-cert-issuer.pub
```

Expected output: `✗ INVALIDE`.

The tamper script bumps `kappa_observed` by 0.0001 — a value change
small enough to be statistically plausible but catastrophic to the
signature.

---

## Part 5 — Compliance evidence packages

### Single-episode DORA / NIS2 report

Track B and Track C both expose `GET /agents` from h7-monitor on port 8000.
Each agent's `id` can be used to download a CBOR attestation envelope:

```bash
ENTITY=$(curl -s http://127.0.0.1:8000/agents | jq -r '.[0].id')

curl -X POST -H "Authorization: Bearer h7-e2e-test-token" \
    http://127.0.0.1:8000/attest/$ENTITY
# Returns: {"png_url": "/attest/.../qr.png", "cbor_url": "/attest/.../cbor"}

curl -H "Authorization: Bearer h7-e2e-test-token" \
    http://127.0.0.1:8000/attest/$ENTITY/cbor \
    -o attestation.cbor

make verify-attest CBOR=attestation.cbor
```

### Signed audit bundle

```bash
make gen-audit-package
# Output: run/audit-package/
#   ├── manifest.json         (signed JSON manifest)
#   ├── alert-*.cal           (every signed alert)
#   ├── baseline.json
#   └── h7-cert-issuer.pub
```

### RFC 3161 timestamps

```bash
make ts-harvest                 # timestamps all .cal in the last 60 minutes via FreeTSA
```

### Non-drift compliance report (24 h)

```bash
make gen-drift-report
# Output: run/reports/drift-report-<timestamp>.json
```

### Full bundle

```bash
make compliance-bundle          # gen-drift-report + ts-harvest in one shot
```

### Regulatory mapping

- **EU AI Act Annex III:** [docs/EU-AI-ACT-TRACEABILITY.md](docs/EU-AI-ACT-TRACEABILITY.md)
- **DORA 2025 Art. 17 / NIS2 Art. 20:** detailed mapping provided in the pilot package; contact `contact@pulsaride.com` for the compliance checklist.

---

## Part 6 — Offline / air-gap operation

Everything except `make setup` (which fetches signed release archives) and
`docker compose up -d` (which pulls the GHCR image) works without
internet access.

```bash
# Before going offline (on a connected machine):
make setup                      # fetches signed binaries once
docker pull ghcr.io/pulsaride/h7-monitor:latest   # for Track B
make seed-offline-baseline      # idempotent fixture seed (no BTF needed)

# After going offline, every demo continues to work:
make calibrate                  # auto-falls-back to the pinned fixture
make up && make attack && make verify
python3 scripts/sim-live-telemetry.py --duration-sec 60 --interval-ms 500
make test
```

`fixtures/H7_RELEASE_SIGNING.pub` is pinned in the repo. **No release
key is ever fetched from the network** — `fetch-release-binaries.sh`
refuses to run if the pinned key file is missing.

USB-stick / air-gap deployment guides are available to pilot customers; contact `contact@pulsaride.com`.

---

## Part 7 — Running the test suite

The suite uses pytest and runs without any kernel, network, or fetched
binary. It is the fastest end-to-end correctness check.

```bash
make dev-setup                  # one-time: creates venv/ + installs pytest
make test                       # 42 tests, ~12 s
```

What gets tested:

| File | Coverage |
|---|---|
| `tests/test_baseline.py` | seed-offline-baseline canonical hash, idempotence, `calibration_source` metadata, fail-closed on missing fixture |
| `tests/test_telemetry.py` | sim-live-telemetry CLI contract, AlertCert v1.1 conformance, kappa bounds, tick monotonicity |
| `tests/test_schema.py` | frozen schema completeness, `additionalProperties: false`, baseline fixture integrity, mandatory document presence |
| `tests/test_repo_integrity.py` | mandatory scripts/docs/fixtures present, no broken cross-repo references, no invented CLI flags |

CI runs the same suite on every push and PR (.github/workflows/e2e.yml).

---

## Part 8 — Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pip install` errors with `externally-managed-environment` | Debian 12+ PEP 668 protection | `make dev-setup` (uses `venv/`) |
| `make test` says `pytest not found` | venv not created yet | `make dev-setup` |
| `make setup` fails verifying SHA256SUMS.sig | Pinned key missing or rotated | Re-clone the repo to restore `fixtures/H7_RELEASE_SIGNING.pub` |
| `make calibrate` skips with `sha256≠pending` | Baseline already calibrated | `make clean && make calibrate` to recalibrate |
| `make up` fails with `Permission denied (eBPF)` | Missing CAP_BPF | Run with `sudo`, kernel ≥ 5.8 |
| `0 alerts` after `make attack` | Threshold too high for this machine | `python3 scripts/attack-noise.py --workers 8 --duration 90` |
| Port 9999 in use | Zombie sinkhole | `ss -ltnp \| grep :9999` then kill the PID |
| Port 8000 in use | Prior `docker compose up -d` | `docker compose down -v` |
| `make verify` reports `INVALIDE` | Tamper test ran or baseline was substituted | This is the expected demo behavior — see [Part 4](#part-4--tamper-detection-demo) |
| Dashboard at `:3001` blank | `docker compose ps` shows h7-monitor exited | `docker compose logs h7-monitor` — usually port conflict or NDJSON path missing |
| Telemetry not appearing in dashboard | sim writing to wrong path | Use `make stream-telemetry`, which writes the path the container reads |

---

## Part 9 — Key files reference

| Path | Purpose |
|---|---|
| `Makefile` | Every orchestration target (`make help`) |
| `docker-compose.yml` | Pulls `ghcr.io/pulsaride/h7-monitor` + runs sinkhole |
| `requirements-test.txt` | pytest>=8.0 |
| `fixtures/baseline.example.json` | Pinned offline-fallback baseline |
| `fixtures/H7_RELEASE_SIGNING.pub` | Pinned Ed25519 release verification key |
| `scripts/sim-live-telemetry.py` | Deterministic AlertCert v1.1 simulator (stdlib only) |
| `scripts/seed-offline-baseline.py` | Offline baseline seeder (stdlib only, no BTF) |
| `scripts/attack-noise.py` | sched_switch load generator + `--vercel-pattern` mode |
| `scripts/demo-sinkhole.py` | Loopback sinkhole on 127.0.0.1:9999 |
| `scripts/tamper-alert.sh` | One-byte tamper script for the rejection demo |
| `scripts/validate-alerts-ndjson.py` | Schema validation against the frozen JSON Schema |
| `scripts/gen-audit-package.py` | Signed audit evidence bundle |
| `scripts/gen-drift-report.py` | 24-hour non-drift compliance report |
| `scripts/ts-request.py` | RFC 3161 timestamps via FreeTSA |
| `docs/schemas/alert-v1.1.json` | Frozen AlertCert v1.1 JSON Schema |
| `docs/demo/DEMO-SNAPSHOT.md` | Annotated NDJSON telemetry across all three phases |
| `THREAT-MODEL.md` | Adversary profiles ADV-1–4, attack surface, mitigations |
| `SECURITY.md` | Vulnerability Disclosure Policy |

---

## What this kit does NOT include

- **`h7-brain` source code** is in a separate private repository. The
  public attestation chain (sensor → NDJSON → `.cal` → CBOR) is fully
  independent of the brain.
- **`attack-vercel.sh` and `launch-k8s-demo.sh`** require a full internal
  monorepo (`p-h7/` + `h7-monitor/` siblings) and will fail on a clean
  clone. They are kept in the tree for maintainer convenience but are
  **not part of the public evaluation path**.
- **`make verify-gate-hardening`** imports the h7-monitor Python module
  directly and therefore needs that backend source. The runtime
  hardening it tests is exercised by every Track B demo, just not
  asserted programmatically.

Everything else in this guide works from a clean clone of this single
repository.

---

Report security findings to **security@pulsaride.com** — see [SECURITY.md](SECURITY.md).
