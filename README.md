# h7-demo-kit

**Public, self-contained demonstration kit for Pulsaride-H7 — kernel-level LLM Agent Hijack detection.**

This repository is the only thing you need to evaluate H7. It pulls signed
binaries from public GitHub Releases and a public container image from
GHCR. No private source access, no cloud account, no internet after first
setup.

```
                  ┌──────────────────────────────────────────────┐
                  │  PUBLIC ARTIFACTS                            │
                  │  • this repo (scripts + fixtures + schema)   │
                  │  • h7-sensor + h7 binaries (signed Release)  │
                  │  • ghcr.io/pulsaride/h7-monitor (container)  │
                  └──────────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌───────────────────────────────────┐
                    │  3 PUBLIC EVALUATION TRACKS       │
                    ├───────────────────────────────────┤
                    │  A. Offline schema + crypto       │   2 min,  no sudo, no Docker
                    │  B. Docker monitor + telemetry    │   5 min,  Docker
                    │  C. Live eBPF sensor              │  15 min,  sudo + Linux 5.8+
                    └───────────────────────────────────┘
```

---

## Quick start (Track A — 2 min, zero infra)

```bash
git clone https://github.com/pulsaride/h7-demo-kit
cd h7-demo-kit
make dev-setup          # creates venv/ + installs pytest (PEP 668 compatible)
make test               # 40 tests across 4 suites (no kernel, no network)
```

You've now validated:
- **`test_schema`** — frozen AlertCert v1.1 JSON Schema + fixture integrity
- **`test_baseline`** — canonical SHA-256 algorithm, idempotence, fail-closed on missing fixture
- **`test_telemetry`** — simulator conformance to AlertCert v1.1, CLI contract, kappa bounds
- **`test_repo_integrity`** — mandatory files present, no broken cross-repo refs, signing key format

---

## Track B — Docker monitor stack (5 min, no sudo)

Brings up the h7-monitor container from GHCR and streams synthetic
AlertCert v1.1 telemetry into it. End result: a live fleet dashboard with
real BREACH events and a CBOR attestation envelope you can verify offline.

```bash
# 1. Pull and start h7-monitor (FastAPI :8000 + Next.js dashboard :3001)
docker compose up -d
docker compose ps            # confirm h7-monitor is Up

# 2. Stream NDJSON telemetry into the volume the monitor reads.
#    NOTE: this command runs until you Ctrl-C it. Let it run for at least
#    60 s in another terminal so the simulator reaches the BREACH phase.
make stream-telemetry        # writes run/alerts/alerts.ndjson at 500 ms cadence

# 3. Confirm the stack is healthy (works headless — no browser needed):
curl -s -o /dev/null -w 'dashboard: HTTP %{http_code}\n' http://127.0.0.1:3001/
curl -s -o /dev/null -w 'backend:   HTTP %{http_code}\n' http://127.0.0.1:8000/agents
curl -s http://127.0.0.1:8000/agents | jq '.[0] | {id, status, kappa, tick}'
# Expect HTTP 200 on both; the agent should reach status: "BREACH" within ~30 s.

# 4. Open the dashboard in a browser (skip on headless/CI runs):
xdg-open http://127.0.0.1:3001 2>/dev/null \
  || open http://127.0.0.1:3001 2>/dev/null \
  || echo "open http://127.0.0.1:3001 in your browser"
```

Stop with `docker compose down -v`.

> **For automated / AI evaluators (Manus, CI, SSH-only):** step 4 is optional.
> The dashboard at `:3001` is a Next.js client UI that proxies `/api/*` to the
> FastAPI backend on `:8000`. All agent state, severity transitions, and
> attestation downloads are reachable directly via the REST API on `:8000`
> (`/agents`, `/attest/{id}`, `/attest/{id}/cbor`). Use the `curl` commands
> in step 3 to confirm the stack is healthy without a browser.

---

## Track C — Live eBPF sensor (15 min, sudo + Linux 5.8+)

The full BREACH path — real `sched_switch` events from your kernel, real
Ed25519-signed `.cal` alerts, real tamper-detection.

```bash
# 1. Fetch signed sensor + verify binaries from public GitHub Releases.
#    Verifies SHA256SUMS.sig against fixtures/H7_RELEASE_SIGNING.pub.
make setup

# 2. Calibrate a baseline. Auto-detects BTF; falls back to the pinned
#    offline fixture on kernels without /sys/kernel/btf/vmlinux.
make calibrate                # ~2 min, sudo if BTF is present

# 3. Start the sensor + loopback sinkhole.
make up                       # sudo (CAP_BPF + CAP_SYS_ADMIN)
make status                   # confirm sensor + sinkhole are up
make watch                    # follow alerts.ndjson in a second terminal

# 4. Run the noise generator → triggers a κ/CUSUM breach.
make attack                   # 60 s, 4 workers
#     or, for the 2026-04-21 supply-chain pattern:
make attack-vercel

# 5. Verify cryptographic attestation on every emitted alert.
make verify                   # Ed25519 sig + baseline_sha256_hex binding

# 6. Show one-byte tamper rejection (the demo highlight).
bash scripts/tamper-alert.sh run/alerts/alert-000001.cal
run/bin/h7 cal verify-alert run/alerts/alert-000001.cal.tampered.cal \
    --public-key run/keys/h7-cert-issuer.pub
# Expected output: ✗ INVALIDE

# 7. Teardown.
make down                     # purges raw logs, keeps signed alerts
```

---

## What every track proves

| Capability | Track A | Track B | Track C |
|---|:---:|:---:|:---:|
| Frozen AlertCert v1.1 schema | ✓ | ✓ | ✓ |
| Canonical SHA-256 binding (`baseline_sha256_hex`) | ✓ | ✓ | ✓ |
| Ed25519-signed `.cal` alerts | — | — | ✓ |
| One-byte tamper rejection | — | — | ✓ |
| Live fleet dashboard | — | ✓ | ✓ |
| CBOR attestation envelope download | — | ✓ | — |
| Real kernel sched_switch detection | — | — | ✓ |
| Offline / air-gap operation | ✓ | partial | ✓ (after `make setup`) |

---

## What this kit does NOT include

Two things are deliberately out of scope for the public kit:

1. **`h7-brain` source code.** The control plane lives in a separate
   private repository. The kit's public demos work because the
   detection chain (kernel sensor → AlertCert v1.1 → signed `.cal`)
   is fully decoupled from the brain; the brain only adds episode
   aggregation and DORA reporting on top.

2. **The `attack-vercel.sh` and `launch-k8s-demo.sh` scripts.** These
   exist in this repo for maintainers running the full internal
   monorepo (`p-h7/` + `h7-monitor/` siblings checked out next to this
   kit). They are not part of the public evaluation path and will fail
   with `h7-brain venv missing` or `h7-monitor not found` on a clean
   clone. See the comment block at the top of each script.

The Ed25519 attestation chain, the schema invariants, and the κ/CUSUM
detector are all observable through the public Tracks A–C above.

---

## Repository layout

```
h7-demo-kit/
├── README.md                     # this file
├── USER-GUIDE.md                 # 9-part step-by-step guide
├── CONTRIBUTING.md               # contributor workflow + hard constraints
├── CODE_OF_CONDUCT.md            # Contributor Covenant 2.1
├── THREAT-MODEL.md               # adversary profiles ADV-1–4, attack surface
├── SECURITY.md                   # Vulnerability Disclosure Policy
├── Makefile                      # all orchestration targets (`make help`)
├── docker-compose.yml            # pulls ghcr.io/pulsaride/h7-monitor (Track B)
├── requirements-test.txt         # pytest>=8.0
├── tests/                        # 40 pytest tests, no kernel/network required
│   ├── test_baseline.py          # canonical hash, idempotence, fail-closed
│   ├── test_telemetry.py         # AlertCert v1.1 conformance, CLI contract
│   ├── test_schema.py            # frozen schema + fixture integrity
│   └── test_repo_integrity.py    # mandatory files, no broken cross-repo refs
├── fixtures/
│   ├── baseline.example.json     # pinned offline-fallback baseline
│   └── H7_RELEASE_SIGNING.pub    # pinned Ed25519 release signing key
├── scripts/
│   ├── sim-live-telemetry.py     # deterministic AlertCert v1.1 simulator
│   ├── seed-offline-baseline.py  # offline baseline (no BTF required)
│   ├── attack-noise.py           # sched_switch load generator + Vercel pattern
│   ├── demo-sinkhole.py          # local loopback sinkhole (127.0.0.1:9999)
│   ├── tamper-alert.sh           # one-byte tamper for rejection demo
│   ├── verify-gate-hardening.py  # FastAPI gateway regression suite
│   ├── gen-audit-package.py      # signed audit evidence bundle
│   ├── gen-drift-report.py       # 24-h non-drift compliance report
│   ├── ts-request.py             # RFC 3161 timestamps via FreeTSA
│   └── …                         # see `make help` for the full list
└── docs/
    ├── PUBLIC-READINESS.md       # public-readiness charter (this kit)
    ├── EU-AI-ACT-TRACEABILITY.md # EU AI Act Annex III mapping
    ├── schemas/
    │   └── alert-v1.1.json       # frozen AlertCert v1.1 JSON Schema
    └── demo/
        └── DEMO-SNAPSHOT.md      # annotated NDJSON across signal phases
```

Operational runbooks (live-demo cue card, USB air-gap variant, full DORA/NIS2 checklist, bug-bounty programme details) ship with the pilot package — contact `contact@pulsaride.com`.

---

## Compliance bundle (one shot)

```bash
make gen-audit-package   # signed manifest + every .cal → run/audit-package/
make gen-drift-report    # 24-h non-drift compliance report → run/reports/
make gen-crl             # Certificate Revocation List (operator use)
make validate-crl        # verify CRL signature
make compliance-bundle   # all of the above in one shot + RFC 3161 timestamps
```

Output: `run/audit-package/` (signed manifest + every `.cal` ever emitted)
and `run/reports/drift-report-<timestamp>.json`.

Mapping to regulation:

- **DORA 2025 Art. 17 (incident detection)** and **NIS2 Art. 20 (significant incident reporting)**: detailed checklist ships with the pilot package; contact `contact@pulsaride.com`.
- **EU AI Act Annex III (high-risk AI logging):** [`docs/EU-AI-ACT-TRACEABILITY.md`](docs/EU-AI-ACT-TRACEABILITY.md)

---

## Honest limitations

1. **`fixtures/baseline.example.json` is pre-calibrated** for a typical
   workstation idle profile. On very different hardware re-run
   `make calibrate` (~2 min). Track A and Track B both work with the
   pinned fixture; only Track C benefits from a fresh calibration.

2. **The κ/CUSUM detector is a kernel-behavior detector**, not a
   malware classifier. The claim is *"we detect kernel-behavior drift
   and namespace-level shell injection"*, never *"we identify a malware
   family"*.

3. **Track C requires a Linux 5.8+ kernel with eBPF CO-RE.** On VMs and
   restricted kernels the sensor cannot run; Tracks A and B remain fully
   functional and offline.

4. **The h7-monitor GHCR image is publicly pullable** but the backend
   Python source is not. `make verify-gate-hardening` and the e2e
   pipeline tests that import the backend module are therefore
   maintainer-only paths.

---

## Links

- [USER-GUIDE.md](USER-GUIDE.md) — full step-by-step user guide
- [SECURITY.md](SECURITY.md) — Vulnerability Disclosure Policy
- [THREAT-MODEL.md](THREAT-MODEL.md) — adversary profiles, attack surface
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributor workflow
- [docs/PUBLIC-READINESS.md](docs/PUBLIC-READINESS.md) — public-readiness charter
- [docs/schemas/alert-v1.1.json](docs/schemas/alert-v1.1.json) — frozen schema
- [docs/demo/DEMO-SNAPSHOT.md](docs/demo/DEMO-SNAPSHOT.md) — annotated telemetry

Bug reports and security findings: **security@pulsaride.com** (see [SECURITY.md](SECURITY.md)).
