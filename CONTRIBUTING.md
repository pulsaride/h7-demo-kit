# Contributing to h7-demo-kit

Thank you for improving the Pulsaride-H7 demo kit. This document covers
the constraints contributors must respect and the workflow to follow.

---

## What lives here

This repository contains:
- **Demo orchestration scripts** (`attack-vercel.sh`, `launch-k8s-demo.sh`)
- **Stdlib-only Python scripts** in `scripts/` (no pip deps in the demo path)
- **Frozen AlertCert v1.1 schema** (`docs/schemas/alert-v1.1.json`)
- **Fixtures and signing keys** (`fixtures/`)
- **Documentation** (`docs/`, `USER-GUIDE.md`, `THREAT-MODEL.md`, etc.)
- **pytest test suite** (`tests/`)

The `h7-brain` control plane is in a separate private repository and is
not required to develop or evaluate this kit. Public demos use the signed
binaries from GitHub Releases (Track C) or the GHCR container image
(Track B); see [USER-GUIDE.md](USER-GUIDE.md).

---

## Hard constraints (see `AGENTS.md`)

1. **No pip dependencies in demo scripts.** `scripts/sim-live-telemetry.py`,
   `scripts/seed-offline-baseline.py`, and the attack scripts use only the
   Python standard library. Tests in `tests/` may use `pytest`.

2. **Schema is frozen.** Do not add or remove fields from
   `docs/schemas/alert-v1.1.json` without an ADR and a version bump to
   `alert-v1.2.json`. The `version: "1.1"` constant in the schema is a
   hard invariant.

3. **Canonical hash algorithm is fixed.** The `sha256` key is excluded from
   the canonical JSON when computing baseline hashes. This algorithm must
   not change without an ADR.

4. **No network fetches at demo time.** All signing keys (`fixtures/H7_RELEASE_SIGNING.pub`)
   and baseline fixtures are pinned in the repo. `fetch-release-binaries.sh`
   is a pre-demo setup step, not a demo-time step.

5. **No nested repos.** `h7-monitor` must remain a sibling directory, never
   a submodule or nested clone.

---

## Development workflow

### 1. Fork and clone

```bash
git clone https://github.com/pulsaride/h7-demo-kit
cd h7-demo-kit
```

### 2. Run the test suite

```bash
pip install pytest
make test           # 40 tests, ~12 s, no kernel/binaries/network required
```

All PRs must pass `make test` before review.

### 3. Check mandatory pre-push invariants

```bash
make verify-gate-hardening       # 3/3 OK
python3 scripts/sim-live-telemetry.py --duration-sec 4 --interval-ms 500
make seed-offline-baseline       # idempotent
```

### 4. Commit style

- One logical change per commit.
- Present tense, imperative mood: `fix(scripts): correct CLI flag in AGENTS.md`
- No `Co-Authored-By:` lines — commits are signed under the human author's
  identity only (see `AGENTS.md`).
- Reference the relevant ADR or issue number if applicable.

### 5. Open a pull request

Use the PR template. CI runs `make e2e-full` and `make verify-gate-hardening`
automatically on every push.

---

## Adding a new script

1. Confirm it belongs in `scripts/` (not a core h7-brain change — those go in `p-h7`).
2. Use only stdlib if it's on the demo critical path.
3. Add a `## help text` comment so `make help` picks it up.
4. Add a corresponding `make test` regression: even a simple `test_<script>_exists` check
   is better than nothing.
5. Update `README.md` repository layout table.

---

## Adding or modifying documentation

- `THREAT-MODEL.md` — add adversary profiles under `§4`, update `§3` attack surface table.
- `docs/EU-AI-ACT-TRACEABILITY.md` — EU AI Act Annex III is the normative reference.
- `docs/PUBLIC-READINESS.md` — public-readiness charter (apply before any new content lands in the public path).
- `USER-GUIDE.md` — keep the troubleshooting table and key files reference current.

---

## Reporting a security vulnerability

Do **not** open a public issue. Email `security@pulsaride.com`. See
[`SECURITY.md`](SECURITY.md) for the full Vulnerability Disclosure Policy.
