# Quickstart

## Two-minute baseline (Track A)

Use this if you want immediate validation with no Docker and no sudo.

```bash
git clone https://github.com/pulsaride/h7-demo-kit
cd h7-demo-kit
make dev-setup
make test
```

What this validates:

- Frozen AlertCert v1.1 schema integrity.
- Canonical SHA-256 behavior and fail-closed baseline handling.
- Telemetry conformance checks from the simulator and tests.

## Local reference docs (this site)

```bash
make docs-setup
make docs-serve
```

Then open `http://127.0.0.1:8088`.

## Build static docs only

```bash
make docs-build
```

This writes static output to `site/`.

## Where to go next

- **Evaluation Tracks** for Track B (Docker monitor) and Track C (live eBPF sensor).
- **Technical Reference** for attestation and schema details.
