# Pulsaride-H7 — Getting Started

> eBPF-native behavioral attestation for Linux AI runtimes.
> This guide covers every path from first contact to a running production system.

---

## Choose your path

| I want to… | Time | Prerequisites | Go to |
|---|---|---|---|
| **Evaluate** — see H7 detect an attack with no hardware commitment | 10 min | Linux or macOS, Docker | [§1 — Evaluation (demo kit)](#1--evaluation-demo-kit) |
| **Install** — put H7 on a real Linux host (staging or production) | 30 min | Linux 5.8+, sudo, license token | [§2 — Production install](#2--production-install) |
| **Integrate** — connect H7 alerts to your SIEM | 15 min | Running H7 instance | [§3 — SIEM integration](#3--siem-integration) |
| **Deploy at scale** — Kubernetes / multi-host | — | Kubernetes cluster | [§4 — Kubernetes](#4--kubernetes) |

---

## 1 — Evaluation (demo kit)

No license, no hardware, no kernel access required for Tracks A and B.

### Prerequisites
- Git
- Docker Engine 20+ + Docker Compose v2
- Python 3.10+ (for the test suite)
- Linux with kernel 5.8+ **only** for Track C (live eBPF sensor)

### Quick start
```bash
git clone https://github.com/pulsaride/h7-demo-kit
cd h7-demo-kit

make dev-setup     # create local Python venv
make test          # 40 tests, ~12 s — no kernel/network required

make setup         # download signed h7-sensor + h7 binaries
make calibrate     # build host baseline (2 min; offline-fallback if no BTF)
docker compose up -d
make attack        # 60-second breach scenario
make verify        # Ed25519 signature verification on every alert
```

Open **http://localhost:3001** — you'll see the breach transition from WARN → CRITICAL → recovery in real time.

### What each track covers

| Track | What you prove | Time |
|---|---|---|
| **A** — schema validation | AlertCert v1.1 frozen schema + Ed25519 signature integrity | 2 min |
| **B** — Docker monitor | Live dashboard (`/agents`, `/stream` WS), BREACH events via simulated telemetry | 5 min |
| **C** — live eBPF sensor | Real kernel scheduling entropy, genuine breach detection, signed `.cal` sidecars | 15 min |
| **D** — operator control plane | `h7ctl doctor`, offline calibration, Splunk HEC forwarding | 10 min |

Full walk-through: [`USER-GUIDE.md`](USER-GUIDE.md)

---

## 2 — Production install

### 2.1 Prerequisites

| Requirement | Minimum | Recommended |
|---|---|---|
| Linux kernel | 5.8 | 5.15+ |
| Architecture | x86_64 | x86_64 / aarch64 |
| Docker Engine | 20.0 | latest |
| Free disk (`/var`) | 2 GB | 10 GB |
| Privileges | sudo | sudo |
| Network | outbound HTTPS (setup only) | can be air-gapped after setup |

BTF (`/sys/kernel/btf/vmlinux`) is **strongly recommended** for the live κ/CUSUM engine. If absent, `h7ctl calibrate` falls back to an offline baseline seed automatically — detection still runs, but the baseline is not host-calibrated.

Operating envelope: hosts sustaining **≥ 2 000 `sched_switch` events per 100 ms tick** under continuous workload (Kafka brokers, OLTP databases, AI inference runtimes, busy ingress proxies). Below this threshold `gate_alpha = false` and the sensor will say so clearly.

### 2.2 Step 1 — Install h7ctl

`h7ctl` is the operator CLI that manages licensing, calibration, and environment diagnostics.

```bash
curl -sSfL https://pulsaride.com/install.sh | sudo sh
```

This script (source: [`public/install.sh`](https://github.com/pulsaride/website/blob/master/public/install.sh)):
1. Downloads the signed `h7ctl` binary for your architecture.
2. Verifies the Ed25519 release signature against a **pinned** key (never fetched from the network).
3. Installs `h7ctl` to `/usr/local/bin/h7ctl`.
4. Creates system directories: `/etc/h7/`, `/etc/pulsaride-h7/`, `/var/lib/pulsaride-h7/baseline/`.
5. Installs the license-validator public key to `/etc/h7/h7-license-validator-k1.pub`.

Verify the install:
```bash
h7ctl --version
h7ctl doctor      # checks kernel, BTF, CAP_BPF, JIT, baseline, status socket
```

`h7ctl doctor` is safe to run at any time — it reads state and prints a colour-coded report; it never writes anything.

> **Root requirement:** `h7ctl doctor` runs as any user (read-only). All other
> subcommands (`auth`, `calibrate`) write to root-owned system paths and need
> `sudo`. The sensor also requires `CAP_BPF` (i.e. `sudo h7-sensor ...`).

### 2.3 Step 2 — Enable eBPF JIT

Required before calibration; the sensor refuses to load without it:

```bash
sudo sysctl -w kernel.bpf_jit_enable=1
# Persist across reboots:
echo 'kernel.bpf_jit_enable=1' | sudo tee /etc/sysctl.d/99-bpf-jit.conf
```

### 2.4 Step 3 — Activate your license

You receive a license token from Pulsaride (format: `eyJhbGc…`). Activate it:

```bash
sudo h7ctl auth "eyJhbGciOiJFZERTQSIsImtpZCI6…"
```

This command:
- Validates the Ed25519 signature **offline** against the validator key at `/etc/h7/h7-license-validator-k1.pub`.
- Prints your tier, namespace quota, and days to expiry.
- Writes `/etc/pulsaride-h7/license.toml`.

```
  [✓] License verified
      tier:           professional
      max_namespaces: 50
      expires:        2027-06-04 (364 days)
      deployed →      /etc/pulsaride-h7/license.toml
```

> **Fail-closed guarantee:** `h7-brain` refuses to start without a valid license outside of `dev/ci/test` environments. There is no silent degraded mode.

### 2.5 Step 4 — Install the sensor

Download the signed Debian package or the static binary from the [latest release](https://github.com/pulsaride/h7-demo-kit/releases/latest):

```bash
# Debian/Ubuntu (recommended for production):
sudo dpkg -i pulsaride-h7_1.0.0_amd64.deb

# Or static binary (any Linux):
curl -sSfL https://github.com/pulsaride/h7-demo-kit/releases/latest/download/h7-sensor-x86_64-unknown-linux-musl.tar.gz \
  | sudo tar -xz -C /usr/local/bin
```

Verify the binary signature (optional but recommended):
```bash
curl -sSfL https://github.com/pulsaride/h7-demo-kit/releases/latest/download/SHA256SUMS -o SHA256SUMS
curl -sSfL https://github.com/pulsaride/h7-demo-kit/releases/latest/download/SHA256SUMS.sig -o SHA256SUMS.sig
curl -sSfL https://github.com/pulsaride/h7-demo-kit/releases/latest/download/H7_RELEASE_SIGNING.pub -o H7_RELEASE_SIGNING.pub
openssl pkeyutl -verify -rawin -pubin -inkey H7_RELEASE_SIGNING.pub \
  -in SHA256SUMS -sigfile SHA256SUMS.sig && echo "Signature OK"
sha256sum -c SHA256SUMS
```

### 2.6 Step 5 — Calibrate the baseline

**The workload must be running at production load** before calibration. Calibration takes 120 seconds and computes a host-specific scheduling-entropy baseline.

```bash
sudo h7ctl calibrate --duration 120
```

Output:
```
▲ Pulsaride-H7 — Baseline Calibration
────────────────────────────────────────────────────────
  [✓] Baseline calibrated and sealed: /var/lib/pulsaride-h7/baseline/current.json
       sha256 = 3f8a1c9b7d4e2f06…
```

If BTF is absent (embedded system, older kernel, or CI):
```bash
sudo h7ctl calibrate --duration 1   # offline fallback, no CAP_BPF needed
```

> Recalibrate whenever the workload profile changes significantly (new services, kernel upgrade, major traffic pattern change). Delete `/var/lib/pulsaride-h7/baseline/current.json` to force a fresh calibration.

### 2.7 Step 6 — Start the control plane

Create `/etc/pulsaride-h7/.env` (never commit to version control):

```bash
H7_LICENSE_KEY=eyJhbGciOiJFZERTQSIsImtpZCI6...   # your license token
H7_HOST=127.0.0.1                                  # bind loopback only in prod
H7_PORT=7700
H7_BRAIN_DB=/var/lib/pulsaride-h7/h7-brain.db
H7_CERT_DIR=/var/lib/pulsaride-h7/episodes
H7_KEYS_DIR=/var/lib/pulsaride-h7/keys
H7_NDJSON_PATH=/var/log/pulsaride-h7/alerts.ndjson
H7_DEBUG=0
H7_ENV=production
```

Start via Docker:
```bash
docker compose -f /etc/pulsaride-h7/docker-compose.yml up -d
```

Or systemd (if installed via `.deb`):
```bash
sudo systemctl enable --now pulsaride-h7-brain
```

Check health:
```bash
curl http://127.0.0.1:7700/health
# {"status":"ok","ndjson_watcher":{"running":true},"k8s_watcher":{"running":false}}
```

### 2.8 Step 7 — Start the monitor (optional)

The monitor provides the compliance dashboard, QR attestation, and SIEM bridge.

```bash
H7_BRAIN_URL=http://127.0.0.1:7700 \
H7_NDJSON_PATH=/var/log/pulsaride-h7/alerts.ndjson \
H7_ATTEST_TOKEN=$(openssl rand -hex 32) \
docker run -d --name h7-monitor --network=host \
  -e H7_BRAIN_URL -e H7_NDJSON_PATH -e H7_ATTEST_TOKEN \
  ghcr.io/pulsaride/h7-monitor:latest
```

Dashboard: **http://localhost:3001**
API docs: **http://localhost:8000/docs**

### 2.9 Step 8 — Run the validation test

```bash
# With the demo-kit cloned locally:
make attack        # synthesises a shell-spawn breach
make verify        # verifies every .cal sidecar signature

# Or manually:
curl http://127.0.0.1:7700/breaches     # should show the episode
curl http://127.0.0.1:8000/agents       # merged κ/CUSUM + behavioral view
```

---

## 3 — SIEM integration

H7 emits **Alert v1.1 NDJSON** to a file and exposes REST endpoints. Connect your SIEM to either.

### Option A — File tail (Splunk, Elastic, Sentinel)

**Alert stream location:** `/var/log/pulsaride-h7/alerts.ndjson`

Each line is a self-contained JSON object:
```json
{
  "event": "H7_ALERT", "version": "1.1",
  "ts_iso": "2026-06-04T20:31:17Z",
  "host": "prod-node-01",
  "kappa": 0.84, "cusum_s": 42.1,
  "severity": "CRITICAL",
  "alert_cert_path": "/var/lib/h7/certs/alert-000412.cal"
}
```

**Key fields to index:** `severity`, `kappa`, `cusum_s`, `host`, `alert_cert_path`, `ts_iso`

#### Splunk HEC
```bash
# Forward live alerts:
python3 scripts/demo-splunk-forward.py \
  --ndjson /var/log/pulsaride-h7/alerts.ndjson \
  --hec-url https://splunk.corp.example:8088/services/collector/event \
  --token <HEC_TOKEN>
```

SPL queries:
```
sourcetype="pulsaride:h7:alert" severity="CRITICAL"
  | table _time host kappa cusum_s alert_cert_path
  | sort - kappa
```

#### Elastic / Sentinel
See `p-h7/siem/` for index templates and DCR definitions.

### Option B — REST poll (any SIEM with webhook/scheduler)

```bash
# Active BREACH episodes:
curl http://127.0.0.1:7700/breaches

# DORA/NIS2 incident report for a specific episode:
curl http://127.0.0.1:7700/episodes/{id}/report

# All DORA reports:
curl http://127.0.0.1:7700/reports/dora
```

### Compliance evidence

Every alert produces a signed `.cal` sidecar. To generate a CBOR QR attestation for regulators (DORA Art. 17, NIS2 Art. 21, EU AI Act Art. 12):

```bash
curl -X POST http://127.0.0.1:8000/attest/{episode_id} \
  -H "Authorization: Bearer <H7_ATTEST_TOKEN>"
# Returns base64url CBOR envelope → scan with any QR reader → offline verify
```

---

## 4 — Kubernetes

H7 runs as a **DaemonSet** — one `h7-brain` pod per node, sharing the host PID namespace to receive QII frames from the sensor.

### Pod annotation (auto-registration)
```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    pulsaride.io/is-ai-runtime: "true"
    pulsaride.io/ns-cookie: "<pid-ns-inode>"   # injected by launch-k8s-demo.sh
    pulsaride.io/service-tag: "inference-svc"
    pulsaride.io/environment: "production"
```

### Manual namespace registration (without annotations)
```bash
curl -X POST http://127.0.0.1:7700/namespaces/$(cat /proc/self/ns/pid | grep -o '[0-9]*') \
  -H "Content-Type: application/json" \
  -d '{"service_tag":"inference-svc","environment":"production","is_ai_runtime":"true"}'
```

Full Kubernetes demo (kind + kubectl + Docker): `launch-k8s-demo.sh`

---

## 5 — Configuration reference

All `H7_*` variables with their defaults:

| Variable | Default | Component | Description |
|---|---|---|---|
| `H7_LICENSE_KEY` | *(required)* | h7-brain | License token (fail-closed if absent in production) |
| `H7_ENV` | `production` | h7-brain | `production` / `dev` / `ci` / `test` |
| `H7_HOST` | `0.0.0.0` | h7-brain | Bind address for REST API |
| `H7_PORT` | `7700` | h7-brain | REST API port |
| `H7_BRAIN_DB` | `/var/lib/pulsaride-h7/h7-brain.db` | h7-brain | SQLite episode store |
| `H7_CERT_DIR` | `/var/lib/pulsaride-h7/episodes` | h7-brain | Episode certificate directory |
| `H7_KEYS_DIR` | `/var/lib/pulsaride-h7/keys` | h7-brain | Ed25519 issuer keypair |
| `H7_NDJSON_PATH` | `/var/log/pulsaride-h7/alerts.ndjson` | h7-brain, h7-monitor | Alert stream |
| `H7_IPC_SOCK` | `/var/run/h7_sensor.sock` | h7-brain | QII frame socket (sensor → brain) |
| `H7_DEBUG` | `0` | h7-brain | `1` enables `/debug/inject` (demo only) |
| `H7_BASELINE_PATH` | `/var/lib/pulsaride-h7/baseline/current.json` | h7ctl, h7-sensor | Sealed baseline |
| `H7_CONFIG_PATH` | `/etc/pulsaride-h7/h7-sensor.toml` | h7ctl doctor | Sensor config |
| `H7_SOCK_PATH` | `/run/pulsaride-h7.sock` | h7ctl doctor | Status socket |
| `H7_PUBKEY_PATH` | `/etc/h7/h7-license-validator-k1.pub` | h7ctl auth | License validator key |
| `H7_LICENSE_TOML` | `/etc/pulsaride-h7/license.toml` | h7ctl auth → h7-brain | Written by `h7ctl auth` |
| `H7_FORCE_OFFLINE` | `0` | h7ctl calibrate | `1` forces offline baseline seed |
| `H7_BRAIN_URL` | `http://127.0.0.1:7700` | h7-monitor | h7-brain endpoint |
| `H7_ATTEST_TOKEN` | *(unset → 503)* | h7-monitor | Bearer token for `POST /attest` |
| `H7_CAL_DIR` | `/var/lib/h7/certs` | h7-monitor | `.cal` sidecar directory |
| `H7_QR_DIR` | `run/qr` | h7-monitor | QR output directory |
| `RUST_LOG` | `info` | h7-sensor | Log verbosity (`error/warn/info/debug/trace`) |

---

## 6 — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `h7ctl doctor` reports `gate_alpha=false` | Workload below 2 000 sched_switch/tick | Use on a production-load host; not a developer workstation |
| `h7-brain` exits immediately at startup | `H7_LICENSE_KEY` unset or expired | Run `h7ctl auth <token>`; check expiry with `h7ctl auth <token>` again |
| `h7-brain` exits `EX_NOPERM` | Dev bypass attempted in production profile | Set `H7_ENV=ci` for dev; obtain a real license for production |
| `h7ctl calibrate` says `Permission denied` | Runs as non-root; baseline dir is root-owned | Use `sudo h7ctl calibrate` |
| `h7ctl calibrate` says BTF absent | Kernel compiled without BTF | Runs offline-fallback automatically; no action needed |
| Port `:9999` already in use | Zombie sinkhole process | `ss -ltnp | grep :9999` then kill; or `make down` first |
| `signature verification failed` on `.cal` | Wrong public key path | Check `H7_PUBKEY_PATH`; key is at `/etc/h7/h7-cert-issuer.pub` (not the license key) |
| `curl /health` returns `degraded` on `ndjson_watcher` | `H7_NDJSON_PATH` file does not exist | Create the file (`touch <path>`) or point to the correct path |
| Dashboard shows `unknown` for service/environment | Namespace not registered | Run `POST /namespaces/{ns_cookie}` or add pod annotations |

More: [`USER-GUIDE.md §Troubleshooting`](USER-GUIDE.md#8-troubleshooting)

---

## 7 — Next steps

| Goal | Resource |
|---|---|
| Full evaluation walk-through | [`USER-GUIDE.md`](USER-GUIDE.md) |
| Production deployment checklist | [`p-h7/onboarding/DEPLOYMENT-GUIDE.md`](https://github.com/pulsaride/p-h7/blob/main/onboarding/DEPLOYMENT-GUIDE.md) |
| Air-gap / offline deployment | [`p-h7/docs/AIR-GAP-OPERATOR-GUIDE.md`](https://github.com/pulsaride/p-h7/blob/main/docs/AIR-GAP-OPERATOR-GUIDE.md) |
| Architecture & component map | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| SIEM connector templates | [`p-h7/siem/`](https://github.com/pulsaride/p-h7/tree/main/siem) |
| Schedule a pilot | [pulsaride.com/pilot](https://pulsaride.com/pilot) |
