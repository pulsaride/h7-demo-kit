#!/usr/bin/env bash
# capture-demo-e2e.sh — drives the full Pulsaride H7 demo for asciinema recording.
#
# Usage:
#   asciinema rec -c "./scripts/capture-demo-e2e.sh" docs/demo/h7-demo-e2e.cast
#
# Env:
#   H7_RELEASE_REPO  (default: pulsaride/p-h7)
#   H7_RELEASE_TAG   (default: v0.7.1-rc1)
#   SKIP_CALIBRATE   (default: auto — skipped if run/baseline.json present)
#   ATTACK_DURATION  (default: 30 — shorter than make default to keep cast tight)

set -euo pipefail

cd "$(dirname "$0")/.."

export H7_RELEASE_REPO="${H7_RELEASE_REPO:-pulsaride/p-h7}"
export H7_RELEASE_TAG="${H7_RELEASE_TAG:-v0.7.1-rc1}"
export H7_SKIP_FETCH="${H7_SKIP_FETCH:-1}"  # binaires déjà stagés dans run/bin/ pour démo offline
ATTACK_DURATION="${ATTACK_DURATION:-30}"

BOLD=$'\033[1m'; CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

banner() {
  echo
  echo "${CYAN}${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
  echo "${CYAN}${BOLD}  $*${RESET}"
  echo "${CYAN}${BOLD}═══════════════════════════════════════════════════════════════${RESET}"
  sleep 1
}

note() { echo "${YELLOW}  → $*${RESET}"; sleep 0.6; }
ok()   { echo "${GREEN}  ✓ $*${RESET}"; sleep 0.4; }

banner "Pulsaride H7 — Démo E2E supply-chain (Vercel 2026-04-21)"
note "Repo release : ${H7_RELEASE_REPO}@${H7_RELEASE_TAG}"
note "Pub key      : fixtures/H7_RELEASE_SIGNING.pub (pinned, sha256 a65e9502…9091)"
sleep 1

banner "1/6  make setup — fetch signed binaries from GitHub Release"
make setup
ok "binaires h7 + h7-sensor téléchargés, signature SHA256SUMS.sig vérifiée"

if [[ -f run/baseline.json ]] && [[ "${SKIP_CALIBRATE:-auto}" != "no" ]]; then
  banner "2/6  baseline déjà calibrée — skip calibrate (mode démo rapide)"
  ok "$(jq -r '"sha256: " + (.sha256 // "n/a")[:32] + "…"' run/baseline.json 2>/dev/null || echo 'baseline présente')"
else
  banner "2/6  make calibrate — Phase Alpha sched_switch (~2 min, sudo)"
  note "Le sensor eBPF observe le noyau et signe une baseline Ed25519."
  make calibrate
  ok "baseline calibrée et signée"
fi

banner "3/6  make up — sensor + sinkhole loopback démarrés"
make up
sleep 2
make status

banner "4/6  make attack-vercel — pattern supply-chain (${ATTACK_DURATION}s)"
note "Simule l'attaque Vercel du 2026-04-21 (beacons HTTP → 127.0.0.1:9999)."
ATTACK_DURATION="${ATTACK_DURATION}" python3 scripts/attack-noise.py \
  --vercel-pattern --duration "${ATTACK_DURATION}" --workers 4 \
  --beacon-url http://127.0.0.1:9999/exfil

banner "5/6  make verify-alert — vérification crypto des AlertCerts"
make verify-alert
ok "toutes les alertes signées et vérifiées"

banner "6/6  make down — arrêt propre"
make down

banner "DÉMO TERMINÉE — récap"
note "Alertes émises : $(ls run/alerts/ 2>/dev/null | wc -l) sidecar(s) .cal"
note "Logs ndjson    : $(wc -l < run/logs/alerts.ndjson 2>/dev/null || echo 0) ligne(s)"
ok "Pulsaride H7 a détecté, certifié et arrêté l'attaque en ${ATTACK_DURATION}s."
sleep 2
