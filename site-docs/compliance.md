# Compliance and Governance

## Public readiness baseline

The project uses a pass/fail readiness charter focused on:

- Friction-free evaluator onboarding.
- Sovereign offline-verifiable evidence.
- Minimal host dependency for core demonstrations.

Reference: `docs/PUBLIC-READINESS.md`.

## Security model and reporting

- Security policy and disclosure workflow: `SECURITY.md`.
- Adversary profiles and attack surface: `THREAT-MODEL.md`.

## Regulatory mapping

- EU AI Act traceability mapping: `docs/EU-AI-ACT-TRACEABILITY.md`.
- DORA/NIS2 evidence generation path via audit and drift reporting commands.

## Evidence commands

```bash
make gen-audit-package
make gen-drift-report
make compliance-bundle
```

Generated evidence is kept under `run/audit-package/` and `run/reports/`.

## Limits and scope

The public kit demonstrates verifiable detection and attestation behavior.

Out-of-scope by design:

- Private control plane source code.
- Internal operational scripts requiring sibling private repositories.
