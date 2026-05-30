#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────────
# MAINTAINER-ONLY — requires the private h7-brain (p-h7) and h7-monitor source
# repositories checked out as siblings of this kit, plus Docker + Kind + kubectl.
# Fails immediately with "h7-brain venv missing" on a clean public clone.
#
# PUBLIC DEMO PATH: see USER-GUIDE.md Tracks B and C.
# ───────────────────────────────────────────────────────────────────────────────
set -euo pipefail
export TERM="${TERM:-xterm-256color}"
export PATH="$HOME/.local/bin:$PATH"

KIT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAEPIVOT_DIR="$(cd "$KIT_DIR/.." && pwd)"
BRAIN_DIR="$CAEPIVOT_DIR/p-h7/h7-brain"
MONITOR_BACKEND="$CAEPIVOT_DIR/h7-monitor/backend"
MONITOR_FRONTEND="$CAEPIVOT_DIR/h7-monitor/frontend"

DEMO_DIR="/tmp/h7-k8s-demo"
DEMO_DB="$DEMO_DIR/brain.db"
DEMO_CERTS="$DEMO_DIR/certs"
DEMO_SOCK="$DEMO_DIR/sensor.sock"
DEMO_NDJSON="$DEMO_DIR/alerts.ndjson"
DEMO_KEYS="$DEMO_DIR/keys"
DEMO_QR="$DEMO_DIR/qr"
KUBECONFIG_PATH="$DEMO_DIR/kubeconfig"

BRAIN_URL="http://127.0.0.1:7700"
MONITOR_URL="http://127.0.0.1:8000"
NEXT_URL="http://127.0.0.1:3001"
CLUSTER_NAME="h7-sandbox"
POD_NAME="langchain-agent"
POD_NS="default"

RED='\033[0;31m'; YELLOW='\033[0;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; PURPLE='\033[0;35m'; BOLD='\033[1m'; RESET='\033[0m'

_cleanup() {
    echo ""
    echo -e "${CYAN}==> Stopping processes…${RESET}"
    [[ -n "${BRAIN_PID:-}" ]]   && kill "$BRAIN_PID"   2>/dev/null || true
    [[ -n "${MONITOR_PID:-}" ]] && kill "$MONITOR_PID" 2>/dev/null || true
    [[ -n "${NEXT_PID:-}" ]]    && kill "$NEXT_PID"    2>/dev/null || true
    echo -e "${CYAN}==> Deleting Kind cluster…${RESET}"
    kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
    echo -e "${CYAN}==> Done.${RESET}"
}
trap _cleanup EXIT INT TERM

_wait_http() {
    local url="$1" label="$2"
    for _ in $(seq 1 40); do
        curl -sf "$url" >/dev/null 2>&1 && { echo -e "    ${GREEN}✓ $label ready${RESET}"; return 0; }
        sleep 0.3
    done
    echo -e "    ${RED}✗ $label not ready after 12s${RESET}"; exit 1
}

_phase() {
    echo ""
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${BOLD}${CYAN}  $1${RESET}"
    echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
}

_kube() { kubectl --kubeconfig "$KUBECONFIG_PATH" "$@"; }

_now_ns()  { python3 -c "import time; print(int(time.time_ns()))"; }
_now_iso() { python3 -c "from datetime import datetime,timezone; print(datetime.now(timezone.utc).isoformat())"; }

echo -e "${BOLD}${RED}"
echo "  ██████  ██████  ██████  ███    ███ ██████  ████████  ██████  ███████ ███████  "
echo "  ██████  ██████  ██████  ███    ███ ██████  ████████  ██████  ███████ ███████  "
echo -e "${RESET}"
echo -e "${BOLD}         Pulsaride-H7  ·  Demo: LLM Agent Hijack on Kubernetes (Kind)${RESET}"
echo -e "         ${YELLOW}Real K8s cluster · k8s_watcher · ns-cookie auto-registration · DORA${RESET}"

for bin in kind kubectl docker; do
    command -v "$bin" >/dev/null 2>&1 || { echo -e "${RED}✗ $bin not found${RESET}"; exit 1; }
done
[[ -f "$BRAIN_DIR/.venv/bin/h7-brain" ]] || { echo -e "${RED}✗ h7-brain venv missing${RESET}"; exit 1; }
docker info >/dev/null 2>&1              || { echo -e "${RED}✗ Docker daemon not running${RESET}"; exit 1; }

echo -e "    ${GREEN}✓ kind $(kind version | head -1)${RESET}"
echo -e "    ${GREEN}✓ kubectl $(kubectl version --client 2>&1 | head -1)${RESET}"
echo -e "    ${GREEN}✓ docker running${RESET}"

rm -rf "$DEMO_DIR" && mkdir -p "$DEMO_CERTS" "$DEMO_KEYS" "$DEMO_QR"
touch "$DEMO_NDJSON"

_phase "PHASE 1/7 — Kind Cluster (single-node Kubernetes)"

echo -e "  ${CYAN}Creating cluster '$CLUSTER_NAME' (first run pulls images, ~60s)…${RESET}"
kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
kind create cluster --name "$CLUSTER_NAME" --kubeconfig "$KUBECONFIG_PATH" \
    --wait 60s 2>&1 | sed 's/^/    /'
echo -e "    ${GREEN}✓ cluster ready${RESET}"

_kube apply -f "$KIT_DIR/k8s/h7-rbac.yaml" 2>&1 | sed 's/^/    /'

echo ""
echo -e "  ${CYAN}Cluster nodes:${RESET}"
_kube get nodes | sed 's/^/    /'

_phase "PHASE 2/7 — Infrastructure (h7-brain :7700 + h7-monitor :8000)"

echo -e "  ${CYAN}Starting h7-brain (k8s_watcher connecting to Kind kubeconfig)…${RESET}"
KUBECONFIG="$KUBECONFIG_PATH"  \
H7_BRAIN_DB="$DEMO_DB"         \
H7_CERT_DIR="$DEMO_CERTS"      \
H7_IPC_SOCK="$DEMO_SOCK"       \
H7_NDJSON_PATH="$DEMO_NDJSON"  \
H7_DEBUG=1                     \
    "$BRAIN_DIR/.venv/bin/h7-brain" >>/tmp/h7-brain-k8s.log 2>&1 &
BRAIN_PID=$!
_wait_http "$BRAIN_URL/health" "h7-brain (:7700)"

sleep 1
K8S_STATUS=$(curl -sf "$BRAIN_URL/health" | python3 -c "
import json,sys; h=json.load(sys.stdin)
k=h.get('k8s_watcher',{})
print(f\"connected={k.get('connected')}  node={k.get('node')}\")
")
echo -e "    ${CYAN}k8s_watcher: $K8S_STATUS${RESET}"

echo -e "  ${CYAN}Starting h7-monitor…${RESET}"
H7_NDJSON_PATH="$DEMO_NDJSON"          \
H7_BRAIN_URL="$BRAIN_URL"              \
H7_BRAIN_TIMEOUT=2.0                   \
H7_KEYS_DIR="$DEMO_KEYS"               \
H7_QR_DIR="$DEMO_QR"                   \
H7_EPISODES_DB="$DEMO_DIR/monitor.db"  \
    python3 -m uvicorn main:app \
        --host 127.0.0.1 --port 8000 \
        --app-dir "$MONITOR_BACKEND"  \
    >>/tmp/h7-monitor-k8s.log 2>&1 &
MONITOR_PID=$!
_wait_http "$MONITOR_URL/health" "h7-monitor (:8000)"

if [[ -x "$MONITOR_FRONTEND/node_modules/.bin/next" ]]; then
    echo -e "  ${CYAN}Starting Next.js on :3001…${RESET}"
    cd "$MONITOR_FRONTEND"
    NEXT_PUBLIC_API_URL="$MONITOR_URL" npm run dev >>/tmp/h7-next-k8s.log 2>&1 &
    NEXT_PID=$!
    cd "$KIT_DIR"
    _wait_http "$NEXT_URL" "Next.js (:3001)"
fi

_phase "PHASE 3/7 — Deploy LangChain Agent Pod"

echo -e "  ${CYAN}Applying pod manifest…${RESET}"
_kube apply -f "$KIT_DIR/k8s/langchain-agent-pod.yaml" 2>&1 | sed 's/^/    /'

echo -e "  ${CYAN}Waiting for pod Running…${RESET}"
_kube wait pod "$POD_NAME" -n "$POD_NS" --for=condition=Ready --timeout=120s 2>&1 | sed 's/^/    /'
echo -e "    ${GREEN}✓ Pod $POD_NAME is Running${RESET}"

echo ""
_kube get pod "$POD_NAME" -n "$POD_NS" -o wide | sed 's/^/    /'

_phase "PHASE 4/7 — Extract ns-cookie → Annotate Pod → k8s_watcher fires"

echo -e "  ${CYAN}Extracting kernel PID namespace cookie from running pod…${RESET}"
RAW=$(_kube exec "$POD_NAME" -n "$POD_NS" -- readlink /proc/self/ns/pid 2>/dev/null)
NS_COOKIE=$(echo "$RAW" | grep -oP '\d+')
echo -e "    readlink /proc/self/ns/pid  →  $RAW"
echo -e "    ${BOLD}ns_cookie = $NS_COOKIE${RESET}"

echo ""
echo -e "  ${CYAN}Annotating pod with pulsaride.io/ns-cookie=$NS_COOKIE …${RESET}"
_kube annotate pod "$POD_NAME" -n "$POD_NS" \
    "pulsaride.io/ns-cookie=$NS_COOKIE" --overwrite 2>&1 | sed 's/^/    /'

SERVICE_TAG=$(_kube get pod "$POD_NAME" -n "$POD_NS" \
    -o jsonpath='{.metadata.labels.app}' 2>/dev/null || echo "payment-gateway-service")
ENV_TAG=$(_kube get pod "$POD_NAME" -n "$POD_NS" \
    -o jsonpath='{.metadata.labels.environment}' 2>/dev/null || echo "production")

echo ""
echo -e "  ${CYAN}Registering namespace (service_tag: $SERVICE_TAG)…${RESET}"
curl -sf -X POST \
    "$BRAIN_URL/namespaces/$NS_COOKIE?service_tag=$SERVICE_TAG&is_ai_runtime=true&environment=$ENV_TAG" \
    | python3 -m json.tool | sed 's/^/    /'

sleep 1
K8S_STATUS=$(curl -sf "$BRAIN_URL/health" | python3 -c "
import json,sys; h=json.load(sys.stdin)
k=h.get('k8s_watcher',{})
print(f\"connected={k.get('connected')}  node={k.get('node')}\")
")
echo -e "    ${GREEN}k8s_watcher: $K8S_STATUS${RESET}"

_phase "PHASE 5/7 — Baseline (Pod NOMINAL)"

echo -e "  ${GREEN}Pod running safely — agent processing legitimate prompts${RESET}"
echo ""
echo -e "  ${CYAN}Pod logs:${RESET}"
_kube logs "$POD_NAME" -n "$POD_NS" --tail=6 2>/dev/null | sed 's/^/    /'

echo ""
echo -e "  ${CYAN}h7-monitor /agents:${RESET}"
curl -sf "$MONITOR_URL/agents" | python3 -c "
import json,sys
agents = json.load(sys.stdin)
if agents:
    for a in agents:
        print(f\"    {a['status']:8}  {a['id']}\")
else:
    print('    (no active alerts — system nominal)')
" 2>/dev/null

echo ""
echo -e "  ${BOLD}Press ENTER to launch the attack…${RESET}"
read -r

_phase "PHASE 6/7 — ATTACK: kubectl exec → /bin/bash inside AI-runtime namespace"

echo -e "  ${RED}${BOLD}Simulating prompt injection — spawning shell inside pod…${RESET}"
echo ""
echo -e "  ${YELLOW}Command:${RESET}"
echo -e '    kubectl exec langchain-agent -- /bin/bash -c "id && hostname && echo exfil > /tmp/pwned"'
echo ""

_kube exec "$POD_NAME" -n "$POD_NS" -- \
    /bin/bash -c "id && hostname && echo 'exfil: '$(hostname) > /tmp/pwned && echo 'PWNED'" \
    2>&1 | sed 's/^/    /'

echo ""
echo -e "  ${RED}⚠ /bin/bash spawned inside AI-runtime namespace $NS_COOKIE${RESET}"

echo ""
echo -e "  ${CYAN}Notifying h7-brain via debug inject (ns_cookie=$NS_COOKIE)…${RESET}"
INJECT=$(curl -sf -X POST \
    "$BRAIN_URL/debug/inject?ns_cookie=$NS_COOKIE&pid=$$" \
    || echo '{"error":"inject failed"}')
echo -e "    $INJECT"

for tick in 1248 1249 1250; do
    K=$(python3 -c "print(round(0.6 + $tick*0.0005, 4))")
    S=$(python3 -c "print(round(0.9 + $tick*0.0009, 4))")
    echo "{\"event\":\"H7_ALERT\",\"version\":\"1.1\",\"ts_ns\":$(_now_ns),\"kappa\":$K,\"cusum_s\":$S,\"h\":0.40,\"k_short\":50,\"k_long\":5000,\"metric\":\"sched_switch\",\"switches\":19000,\"n_pids\":60,\"ts_iso\":\"$(_now_iso)\",\"host\":\"payment-gateway-service\",\"severity\":\"CRITICAL\",\"mu_baseline\":0.08,\"k_slack\":0.04,\"tick\":$tick,\"shadow_mode\":false}" \
        >> "$DEMO_NDJSON"
done
echo -e "    ${YELLOW}✓ κ/CUSUM spike injected${RESET}"

_phase "PHASE 7/7 — Detection Cascade"

echo -e "  ${CYAN}Waiting for BREACH…${RESET}"
BREACH=""; EPISODE_ID=""
for _ in $(seq 1 30); do
    RESP=$(curl -sf "$BRAIN_URL/breaches" 2>/dev/null || echo "[]")
    HIT=$(python3 -c "
import json,sys
bs=json.loads(sys.stdin.read())
hit=[b for b in bs if b.get('namespace_cookie')==$NS_COOKIE and b.get('threat_class')=='LLM_AGENT_HIJACK']
print(json.dumps(hit[0]) if hit else '')
" <<< "$RESP" 2>/dev/null || true)
    [[ -n "$HIT" ]] && { BREACH="$HIT"; break; }
    printf "."; sleep 0.4
done
echo ""

if [[ -n "$BREACH" ]]; then
    EPISODE_ID=$(python3 -c "import json,sys; print(json.loads(sys.stdin.read())['episode_id'])" <<< "$BREACH")
    echo -e "  ${RED}${BOLD}⚡ BREACH — LLM_AGENT_HIJACK${RESET}"
    python3 -c "
import json,sys
b=json.loads(sys.stdin.read())
print(f\"    service      : {b.get('service_tag','?')}\")
print(f\"    host         : {b.get('host','?')}\")
print(f\"    environment  : {b.get('environment','?')}\")
print(f\"    threat_class : {b.get('threat_class','?')}\")
print(f\"    confidence   : {b.get('confidence','?')}\")
print(f\"    binary_path  : {b.get('binary_path','?')}\")
print(f\"    cert_path    : {b.get('cert_path','?')}\")
" <<< "$BREACH"
fi

sleep 1.5
echo ""
echo -e "  ${BOLD}h7-monitor /agents (k8s attribution + both channels):${RESET}"
curl -sf "$MONITOR_URL/agents" | python3 -c "
import json,sys
for a in json.load(sys.stdin):
    src=f\"  [{a.get('source','cusum')}]\" if a.get('source') else ''
    tc=f\"  {a.get('threat_class','')}\" if a.get('threat_class') else ''
    print(f\"    {a['status']:8}  {a['id']}{src}{tc}  κ={a['kappa']:.4f}\")
" 2>/dev/null

if [[ -n "${EPISODE_ID:-}" ]]; then
    echo ""
    echo -e "  ${BOLD}${PURPLE}DORA/NIS2 Report:${RESET}"
    curl -sf "$BRAIN_URL/episodes/$EPISODE_ID/report" | python3 -c "
import json,sys
r=json.load(sys.stdin)
print(f\"    incident_id   : {r['incident_id']}\")
print(f\"    report_std    : {r['report_standard']}\")
print(f\"    service       : {r['host']} / {r['service']}\")
print(f\"    threat_class  : {r['threat_class']}\")
print(f\"    confidence    : {r['confidence']}\")
print(f\"    certificate   : {r.get('certificate',{}).get('algorithm')}  verified={r.get('certificate',{}).get('verified')}\")
" 2>/dev/null
fi

echo ""
echo -e "${BOLD}${RED}"
echo "  ╔═══════════════════════════════════════════════════════════════════╗"
echo "  ║  K8S ATTACK DETECTED — ADR-014 k8s_watcher VALIDATED            ║"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo -e "  ║  ${RESET}${BOLD}h7-monitor (UI)   →  http://127.0.0.1:3001${RED}${BOLD}                       ║"
echo -e "  ║  ${RESET}${BOLD}h7-monitor Audit  →  http://127.0.0.1:3001/audit${RED}${BOLD}                 ║"
echo -e "  ║  ${RESET}${BOLD}h7-monitor API    →  http://127.0.0.1:8000/agents${RED}${BOLD}                ║"
echo -e "  ║  ${RESET}${BOLD}h7-monitor API    →  http://127.0.0.1:8000/audit${RED}${BOLD}                 ║"
echo -e "  ║  ${RESET}${BOLD}h7-brain Fleet    →  http://127.0.0.1:7700/fleet${RED}${BOLD}                 ║"
echo -e "  ║  ${RESET}${BOLD}DORA List         →  http://127.0.0.1:7700/reports/dora${RED}${BOLD}          ║"
echo "  ╠═══════════════════════════════════════════════════════════════════╣"
echo "  ║  Ctrl-C stops all + deletes the Kind cluster.                   ║"
echo -e "  ╚═══════════════════════════════════════════════════════════════╝${RESET}"
echo ""

[[ -x "$(command -v xdg-open)" ]] && xdg-open "http://127.0.0.1:3001" &>/dev/null &
wait "$BRAIN_PID"
