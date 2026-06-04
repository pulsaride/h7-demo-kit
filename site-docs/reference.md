# Technical Reference

## Key make targets

- `make setup`: fetch signed binaries and generate runtime keys/config.
- `make calibrate`: generate baseline from local kernel activity or fallback fixture.
- `make up` / `make down`: start and stop sensor + sinkhole flow.
- `make verify`: verify generated alerts and schema conformance.
- `make compliance-bundle`: produce signed compliance artifacts.

## Runtime and evidence paths

- `run/baseline.json`: calibrated baseline.
- `run/logs/alerts.ndjson`: telemetry stream.
- `run/alerts/*.cal`: signed alerts.
- `run/audit-package/`: generated audit evidence package.
- `run/reports/`: drift/compliance reports.

## APIs used during Track B

- `GET /agents` on port 8000: current fleet state.
- `POST /attest/{id}`: create attestation artifacts.
- `GET /attest/{id}/cbor`: download CBOR attestation envelope.

Note: attestation endpoints are guarded by `H7_ATTEST_TOKEN`.

## Schemas and docs

- Alert schema: `docs/schemas/alert-v1.1.json`
- Demo snapshot: `docs/demo/DEMO-SNAPSHOT.md`
- Public readiness: `docs/PUBLIC-READINESS.md`
- EU AI Act mapping: `docs/EU-AI-ACT-TRACEABILITY.md`

## Repository quick map

- `scripts/`: telemetry simulation, verification, reporting, packaging.
- `attacks/`: dedicated attack scenario scripts.
- `tests/`: no-kernel/no-network validation tests.
- `fixtures/`: baseline fixture and release signing public key.
- `docs/`: governance, traceability, schema, and demo artifacts.
