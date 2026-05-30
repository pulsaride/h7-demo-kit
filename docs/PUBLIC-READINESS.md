# Public Readiness Charter — h7-demo-kit

This document defines the non-negotiable standards that any artifact must
satisfy before being placed in the public evaluation path.

---

## I. The Golden Rule: "Show Ingredients, Guard the Recipe"

| PUBLIC (Showcase) | PRIVATE (Vault) |
|---|---|
| Autonomous demo kit (`h7-demo-kit`) | Engine source code (`p-h7`, `bgte/`) |
| Executable Docker images (h7-monitor) | Full API endpoint mapping |
| Security primitives: **eBPF, Ed25519, CBOR, CUSUM** | Production filesystem topology |

---

## II. Four Documentation Rules

### 1. Path Abstraction (No Blueprinting)
- ❌ Hardcoded system paths (`/var/log/pulsaride-h7/alerts.ndjson`)
- ✅ Environment variables (`$H7_LOG_DIR/alerts.ndjson`) + ephemeral volumes

### 2. Endpoint Reduction (API Reduction)
- ❌ Full GET/POST/WS route list in public docs
- ✅ Entry point (dashboard URL) + essential compliance endpoints only; full OpenAPI at `/docs`

### 3. Heuristic Shadowing (Threshold Protection)
- ❌ Alert constants in plaintext (`_BREACH_MULT=3.0`)
- ✅ `os.getenv("H7_BREACH_MULT", "<banal-default>")` in image; real values injected via compose `# DEMO OVERRIDE`

### 4. GTM Alignment (No Academic Jargon)
- ❌ arXiv references, `Hodge-Laplacian`, `β₁ directed`, `simplicial complex`
- ✅ Business glossary: see `docs/sales/GLOSSAIRE-METIER.md`

---

## III. Public Readiness Checklist (binary pass/fail)

```
[ Friction ZERO ]        [ Total Sovereignty ]    [ Zero Host Dependency ]
One clone, one 'up',     No external ping,        Ephemeral keys via
zero GitHub token.       100% offline-verifiable. named Docker volumes.
```

A kit is NOT ready if the evaluator must:
- Create a token or request org access
- Edit a config file before running
- Have internet access beyond first `docker compose up` (RFC 3161 timestamps are optional, not on the 5-minute path)

---

## IV. Last audit

| Date | Result | Notes |
|---|---|---|
| 2026-05-30 | ✅ PASS — all 3 criteria and 4 rules | Tracks A/B/C validated from cold clone |
