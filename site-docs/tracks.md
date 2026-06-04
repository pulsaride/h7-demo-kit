# Evaluation Tracks

## Track A: Offline schema + crypto checks (2 min)

No Docker, no kernel access, no sudo.

```bash
make dev-setup
make test
```

Core evidence produced:

- Schema and fixture integrity checks.
- Deterministic baseline seed behavior.
- Canonical hash compatibility.

## Track B: Docker monitor + telemetry stream (5 min)

Use the public monitor image and synthetic telemetry.

```bash
docker compose up -d
make stream-telemetry
```

In another terminal:

```bash
curl -s -o /dev/null -w 'dashboard: HTTP %{http_code}\n' http://127.0.0.1:3001/
curl -s -o /dev/null -w 'backend:   HTTP %{http_code}\n' http://127.0.0.1:8000/agents
curl -s http://127.0.0.1:8000/agents | jq '.[0] | {id, status, kappa, tick}'
```

Expected behavior:

- Agent state transitions through nominal and breach phases.
- Live dashboard and API both report active telemetry.

Stop:

```bash
docker compose down -v
```

## Track C: Live eBPF sensor (15 min)

Requires Linux 5.8+ and sudo.

```bash
make setup
make calibrate
make up
make watch
```

Trigger the attack path:

```bash
make attack
# or
make attack-vercel
```

Verify signed alerts:

```bash
make verify
```

Teardown:

```bash
make down
```

## Tamper demonstration

```bash
bash scripts/tamper-alert.sh run/alerts/alert-000001.cal
run/bin/h7 cal verify-alert run/alerts/alert-000001.cal.tampered.cal \
  --public-key run/keys/h7-cert-issuer.pub
```

Expected: invalid signature after one-byte modification.
