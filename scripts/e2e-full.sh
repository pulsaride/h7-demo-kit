#!/usr/bin/env bash
# e2e-full.sh — full pipeline smoke test without kernel sensor
#
# Steps (all without sudo / eBPF):
#   1. Seed NDJSON via sim-live-telemetry.py
#   2. Start h7-monitor FastAPI backend
#   3. GET /agents — verify data visible
#   4. POST /attest/{id} — verify QR attestation
#   5. GET /attest/{id}/cbor — verify CBOR download
#   6. validate-alerts-ndjson.py — schema check
#   7. gen-drift-report.py — compliance report
#   8. gen-audit-package.py — audit bundle
#   9. Shutdown backend
#
# Exit 0 if all steps pass.
#
# Environment overrides:
#   H7_MONITOR_BACKEND_DIR  path to h7-monitor/backend (default: ../../h7-monitor/backend)
#   H7_ATTEST_TOKEN         Bearer token for /attest (default: h7-e2e-test-token)
#   H7_E2E_PORT             backend port (default: 18007)

set -euo pipefail

# ─── Resolve paths ───────────────────────────────────────────────────────────
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
KIT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
MONITOR_BACKEND="${H7_MONITOR_BACKEND_DIR:-$KIT_DIR/../../h7-monitor/backend}"
PORT="${H7_E2E_PORT:-18007}"
TOKEN="${H7_ATTEST_TOKEN:-h7-e2e-test-token}"

RUN_DIR="$KIT_DIR/run"
LOGS_DIR="$RUN_DIR/logs"
ALERTS_DIR="$RUN_DIR/alerts"
KEYS_DIR="$RUN_DIR/keys"
QR_DIR="$RUN_DIR/qr"
BASELINE="$RUN_DIR/baseline.json"

BACKEND_PID=""
PASS=0
FAIL=0

pass() { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }

# ─── Cleanup ─────────────────────────────────────────────────────────────────
cleanup() {
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    rm -f /tmp/h7-e2e.cbor
}
trap cleanup EXIT

# ─── Pre-flight ──────────────────────────────────────────────────────────────
echo "═══ h7 e2e-full ═════════════════════════════════════════════════════════"
echo "  monitor backend : $MONITOR_BACKEND"
echo "  port            : $PORT"
echo "  token           : ${TOKEN:0:8}…"
echo "═══════════════════════════════════════════════════════════════════════════"

command -v uvicorn >/dev/null 2>&1 || { echo "[e2e] ERROR: uvicorn not found (pip install uvicorn)"; exit 1; }
command -v curl    >/dev/null 2>&1 || { echo "[e2e] ERROR: curl not found"; exit 1; }
[ -d "$MONITOR_BACKEND" ]          || { echo "[e2e] ERROR: $MONITOR_BACKEND not found"; exit 1; }

mkdir -p "$LOGS_DIR" "$ALERTS_DIR" "$KEYS_DIR" "$QR_DIR"

# ─── Offline baseline ────────────────────────────────────────────────────────
if [ -f "$BASELINE" ] && python3 -c "
import json,sys
d=json.load(open('$BASELINE'))
sys.exit(0 if d.get('sha256','pending')!='pending' else 1)
" 2>/dev/null; then
    true  # baseline already valid, skip seeding
else
    echo "[e2e] Seeding offline baseline (BTF fallback)…"
    python3 "$SCRIPT_DIR/seed-offline-baseline.py" \
        --fixture "$KIT_DIR/fixtures/baseline.example.json" \
        --output  "$BASELINE"
fi

# ─── Signing keys ────────────────────────────────────────────────────────────
if [ ! -f "$KEYS_DIR/h7-cert-issuer.sec" ]; then
    echo "[e2e] Generating Ed25519 signing keys…"
    openssl genpkey -algorithm Ed25519 -out "$KEYS_DIR/h7-cert-issuer.sec" 2>/dev/null
    chmod 600 "$KEYS_DIR/h7-cert-issuer.sec"
    openssl pkey -in "$KEYS_DIR/h7-cert-issuer.sec" -pubout \
        -out "$KEYS_DIR/h7-cert-issuer.pub" 2>/dev/null
fi

# ═══ Step 1: seed NDJSON ════════════════════════════════════════════════════
echo ""
echo "── Step 1: Seed NDJSON via sim-live-telemetry.py (5s, 100ms interval)"
> "$LOGS_DIR/alerts.ndjson"
python3 "$SCRIPT_DIR/sim-live-telemetry.py" \
    --output      "$LOGS_DIR/alerts.ndjson" \
    --interval-ms 100 \
    --duration-sec 5

NDJSON_LINES=$(wc -l < "$LOGS_DIR/alerts.ndjson" | tr -d ' ')
if [ "$NDJSON_LINES" -gt 0 ]; then
    pass "alerts.ndjson has $NDJSON_LINES lines"
else
    fail "alerts.ndjson is empty after simulation"
    exit 1
fi

# ═══ Step 2: start backend ══════════════════════════════════════════════════
echo ""
echo "── Step 2: Start h7-monitor backend on port $PORT"
(
    cd "$MONITOR_BACKEND"
    H7_NDJSON_PATH="$LOGS_DIR/alerts.ndjson" \
    H7_ATTEST_TOKEN="$TOKEN"                 \
    H7_QR_DIR="$QR_DIR"                      \
    H7_KEYS_DIR="$KEYS_DIR"                  \
        uvicorn main:app \
            --host 127.0.0.1 \
            --port "$PORT"   \
            --log-level error 2>/dev/null
) &
BACKEND_PID=$!

# Wait up to 20s for /health
READY=0
for _ in $(seq 1 40); do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        READY=1; break
    fi
    sleep 0.5
done
if [ "$READY" -eq 1 ]; then
    pass "backend ready on port $PORT"
else
    fail "backend did not become ready within 20s"
    exit 1
fi

# ═══ Step 3: GET /agents ════════════════════════════════════════════════════
echo ""
echo "── Step 3: GET /agents"
AGENTS_JSON=$(curl -sf "http://127.0.0.1:${PORT}/agents")
AGENT_COUNT=$(echo "$AGENTS_JSON" | python3 -c \
    "import sys,json; print(len(json.load(sys.stdin)))")
ENTITY_ID=$(echo "$AGENTS_JSON" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)[0]['id'])")
if [ "$AGENT_COUNT" -gt 0 ]; then
    pass "/agents returned $AGENT_COUNT agent(s); top entity: $ENTITY_ID"
else
    fail "/agents returned empty list"
    exit 1
fi

# ═══ Step 4: POST /attest ════════════════════════════════════════════════════
echo ""
echo "── Step 4: POST /attest/$ENTITY_ID"
ATTEST_JSON=$(curl -sf -X POST \
    -H "Authorization: Bearer $TOKEN" \
    "http://127.0.0.1:${PORT}/attest/${ENTITY_ID}")
CBOR_URL=$(echo "$ATTEST_JSON" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)['cbor_url'])")
PNG_URL=$(echo "$ATTEST_JSON" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)['png_url'])")
if [ -n "$CBOR_URL" ] && [ -n "$PNG_URL" ]; then
    pass "POST /attest → png_url=$PNG_URL  cbor_url=$CBOR_URL"
else
    fail "POST /attest response missing png_url or cbor_url"
    exit 1
fi

# ═══ Step 5: GET /attest/{id}/cbor ══════════════════════════════════════════
echo ""
echo "── Step 5: GET $CBOR_URL"
HTTP_CODE=$(curl -sf \
    -H "Authorization: Bearer $TOKEN" \
    -o /tmp/h7-e2e.cbor \
    -w "%{http_code}" \
    "http://127.0.0.1:${PORT}${CBOR_URL}" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    CBOR_SIZE=$(wc -c < /tmp/h7-e2e.cbor | tr -d ' ')
    pass "CBOR download 200 ($CBOR_SIZE bytes)"
else
    fail "CBOR download returned HTTP $HTTP_CODE"
    exit 1
fi

# ═══ Step 6: validate NDJSON schema ═════════════════════════════════════════
echo ""
echo "── Step 6: validate-alerts-ndjson.py"
if python3 "$SCRIPT_DIR/validate-alerts-ndjson.py" "$LOGS_DIR/alerts.ndjson"; then
    pass "NDJSON schema validation OK"
else
    fail "NDJSON schema validation FAILED"
    exit 1
fi

# ═══ Step 7: gen-drift-report ════════════════════════════════════════════════
echo ""
echo "── Step 7: gen-drift-report"
if python3 "$SCRIPT_DIR/gen-drift-report.py" \
        --alerts-ndjson "$LOGS_DIR/alerts.ndjson" \
        --baseline      "$BASELINE" \
        --keys-dir      "$KEYS_DIR" \
        --output-dir    "$RUN_DIR/reports"; then
    pass "drift report generated"
else
    fail "gen-drift-report FAILED"
    exit 1
fi

# ═══ Step 8: gen-audit-package ═══════════════════════════════════════════════
echo ""
echo "── Step 8: gen-audit-package"
if python3 "$SCRIPT_DIR/gen-audit-package.py" \
        --alerts-ndjson "$LOGS_DIR/alerts.ndjson" \
        --alerts-dir    "$ALERTS_DIR" \
        --baseline      "$BASELINE" \
        --pub-key       "$KEYS_DIR/h7-cert-issuer.pub" \
        --output-dir    "$RUN_DIR/audit-package"; then
    pass "audit package generated"
else
    fail "gen-audit-package FAILED"
    exit 1
fi

# ═══ Summary ═════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════════════════"
echo "  PASSED: $PASS / $((PASS + FAIL))"
if [ "$FAIL" -gt 0 ]; then
    echo "  FAILED: $FAIL"
    echo "═══════════════════════════════════════════════════════════════════════════"
    exit 1
fi
echo "  ✓ e2e-full PASSED"
echo "═══════════════════════════════════════════════════════════════════════════"
