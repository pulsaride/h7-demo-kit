# Vulnerability Disclosure Policy (VDP) — Pulsaride-H7

At Pulsaride, we believe that security is a collaborative, continuous process.
If you are a security researcher, auditor, or user and have discovered a
vulnerability or flaw in the `h7-demo-kit` or in our core behavioral
attestation primitives, we appreciate your help in disclosing it to us
responsibly.

## Scope

This repository (`h7-demo-kit`) is a sandboxed technical demonstration
environment designed to run strictly within isolated local boundaries
(`127.0.0.1`). The scope of this VDP covers:

- The simulation scripts under `scripts/` (including the `--vercel-pattern`
  mode of `attack-noise.py`).
- The `Makefile` orchestration and `docker-compose.yml` topology.
- The verification logic exposed through the public `h7 verify` binary
  distributed alongside this kit.
- Any documented cryptographic claim about `.cal` calibration and alert
  certificates (Ed25519 signature, `baseline_sha256_hex` binding,
  schema-versioned canonical JSON).

If you discover a method to break the confinement of the simulation scripts,
to exfiltrate data outside `127.0.0.1`, or to **forge a valid `.cal` alert
certificate without holding the corresponding Ed25519 issuer private key**,
please report it immediately.

### Out of scope

- Denial-of-service against your own local machine via the simulation
  scripts (they are designed to stress the scheduler; that is the point).
- Issues in the private `h7-core` / `h7-sensor` source code (not published
  in this repository — report separately via the same contact channel).
- Theoretical adversarial-ML attacks under the κ threshold (acknowledged
  limitation, see [`THREAT-MODEL.md §4.3`](THREAT-MODEL.md#43-adv-3--adaptive-kappa-evasion)).

## Reporting a vulnerability

- **Do NOT open a public GitHub Issue** for security flaws or potential
  exploits.
- Email your encrypted findings to: **security@pulsaride.com**
- Include a detailed proof-of-concept (PoC), step-by-step reproduction
  instructions, the SHA-256 of the affected binary or certificate file
  if applicable, and any relevant log excerpts.
- PGP key fingerprint for encrypted disclosure will be published alongside
  the first signed release tag.

## Our commitment

- We will acknowledge receipt of your vulnerability report within
  **72 hours** (business days).
- We will provide a transparent timeline for triage, remediation, and
  validation, and will keep you informed at each milestone.
- We coordinate disclosure timelines with reporters; the default
  embargo window is **90 days** unless active exploitation is observed.
- A private Bug Bounty program is being structured; contact
  `security@pulsaride.com` for the current scope and rewards pool.
  Valid, novel, and high-impact reports concerning the cryptographic
  attestation chain may qualify.

## Safe harbor

Pulsaride will not pursue legal action against researchers who:

- Make a good-faith effort to comply with this policy.
- Do not exploit findings beyond what is strictly necessary to demonstrate
  the issue.
- Respect user privacy and data confidentiality.
- Refrain from public disclosure before coordinated remediation.

Thank you for helping us keep runtime agent infrastructures secure.
