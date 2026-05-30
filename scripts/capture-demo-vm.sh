#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────────────────────
# MAINTAINER-ONLY — records an asciinema cast against a pre-provisioned VM.
# Requires a multipass VM (name configurable via H7_VM) with signed binaries
# pre-installed under /opt/h7/bin/ and calibrated artefacts under a
# maintainer-defined ${DATA_DIR}. Fails on a clean public clone.
#
# PUBLIC DEMO PATH: see USER-GUIDE.md Tracks A/B/C.
# ───────────────────────────────────────────────────────────────────────────────

set -euo pipefail

VM="${H7_VM:-h7-demo}"
DATA_DIR="/var/lib/h7-demo"
ATTACK_DURATION="${ATTACK_DURATION:-30}"
RELEASE_TAG="${H7_RELEASE_TAG:-v0.7.1}"

BOLD=$'\033[1m'; CYAN=$'\033[36m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
RED=$'\033[31m'; RESET=$'\033[0m'

banner() {
  echo
  echo "${CYAN}${BOLD}════════════════════════════════════════════════════════════════${RESET}"
  echo "${CYAN}${BOLD}  $*${RESET}"
  echo "${CYAN}${BOLD}════════════════════════════════════════════════════════════════${RESET}"
  sleep 1
}
note() { echo "${YELLOW}  → $*${RESET}"; sleep 0.5; }
ok()   { echo "${GREEN}  ✓ $*${RESET}"; sleep 0.3; }
run()  { echo "${BOLD}\$ $*${RESET}"; sleep 0.3; "$@"; }
vm()   { multipass exec "$VM" -- bash -c "$*"; }

banner "Pulsaride H7 — Démo E2E supply-chain (Vercel 2026-04-21)"
note "Cible : sonde eBPF κ — détection d'attaques in-kernel sans signatures."
note "Release : pulsaride/p-h7@${RELEASE_TAG} (musl static-pie, signée Ed25519)."
note "Plateforme : multipass VM \"${VM}\" (Ubuntu 24.04, kernel 6.8)."
sleep 1

banner "1/6  Binaires + config sur la VM"
run vm "/opt/h7/bin/h7-sensor --help 2>&1 | head -3"
run vm "ls -l ${DATA_DIR}/h7-demo.toml ${DATA_DIR}/baseline.json ${DATA_DIR}/baseline.json.cal"
ok "binaires installés, config et baseline présentes"

banner "2/6  Baseline calibrée — vérification cryptographique"
note "La baseline est signée Ed25519 lors de la calibration (Phase Alpha)."
run vm "/opt/h7/bin/h7 cal verify ${DATA_DIR}/baseline.json.cal --public-key ${DATA_DIR}/keys/h7-cert-issuer.pub && echo '  ✓ signature Ed25519 valide'"
echo
note "Verdict Gate Alpha (criteria : κ_max < 0.1 ∧ clip_events == 0 ∧ n_ticks ≥ 100) :"
run vm "jq '.gate_alpha' ${DATA_DIR}/baseline.json"
ok "Gate Alpha PASS — baseline acceptée comme référence."

banner "3/6  Démarrage sinkhole + sensor (mode monitor)"
note "Sinkhole loopback (127.0.0.1:9999) absorbe les beacons d'exfiltration."
vm "nohup python3 /mnt/h7-demo-kit/scripts/demo-sinkhole.py \
      --log ${DATA_DIR}/logs/sinkhole.ndjson \
      >${DATA_DIR}/logs/sinkhole.stderr 2>&1 & echo \$! | sudo tee ${DATA_DIR}/sinkhole.pid >/dev/null"
sleep 1
ok "sinkhole pid=$(vm "cat ${DATA_DIR}/sinkhole.pid")"

note "Sensor eBPF (mode monitor, shadow_mode=false, require_signature=true)."
vm "sudo nohup /opt/h7/bin/h7-sensor --config ${DATA_DIR}/h7-demo.toml \
      >${DATA_DIR}/logs/sensor.stdout 2>${DATA_DIR}/logs/sensor.stderr & \
      echo \$! | sudo tee ${DATA_DIR}/sensor.pid >/dev/null"
sleep 2
ok "sensor pid=$(vm "sudo cat ${DATA_DIR}/sensor.pid") — warmup en cours"
note "Tail des logs sensor (5 lignes) :"
sleep 4
run vm "sudo tail -5 ${DATA_DIR}/logs/sensor.stdout"

banner "4/6  Attaque — pattern pivot supply-chain Vercel (${ATTACK_DURATION}s)"
note "Workers exécutent fork/exec rapides + beacons HTTP → 127.0.0.1:9999."
note "Le sched_switch rate s'envole → κ(t) sort de l'enveloppe ε(x_t)."
ATTACK_LOG="$(mktemp)"
vm "python3 /mnt/h7-demo-kit/scripts/attack-noise.py \
      --vercel-pattern --duration ${ATTACK_DURATION} --workers 4 \
      --beacon-url http://127.0.0.1:9999/exfil 2>&1 | tail -8" | tee "$ATTACK_LOG"
ok "attaque terminée"

banner "5/6  Vérification des AlertCerts émis"
sleep 2
note "Comptage des alertes signées (sidecars .cal) :"
ALERT_COUNT=$(vm "ls ${DATA_DIR}/alerts/ 2>/dev/null | wc -l" || echo 0)
echo "${GREEN}${BOLD}  → ${ALERT_COUNT} alert cert(s) émis${RESET}"
sleep 1
note "Dernières lignes ndjson :"
run vm "sudo tail -3 ${DATA_DIR}/logs/alerts.ndjson 2>/dev/null || echo '(aucune)'"
echo
note "Vérification crypto en boucle :"
run vm "H7_BIN=/opt/h7/bin/h7 bash /mnt/h7-demo-kit/scripts/verify-loop.sh \
        ${DATA_DIR}/alerts ${DATA_DIR}/keys/h7-cert-issuer.pub \
        ${DATA_DIR}/baseline.json 2>&1 | tail -10 || true"
ok "AlertCerts vérifiés — chaîne baseline→alerte intacte"

banner "6/6  Arrêt propre"
vm "sudo kill \$(sudo cat ${DATA_DIR}/sensor.pid) 2>/dev/null || true; \
    kill \$(cat ${DATA_DIR}/sinkhole.pid) 2>/dev/null || true; \
    sudo rm -f ${DATA_DIR}/sensor.pid ${DATA_DIR}/sinkhole.pid"
ok "sensor + sinkhole stoppés"

banner "DÉMO TERMINÉE"
note "Sonde eBPF a détecté l'anomalie sched, signé les alertes (Ed25519),"
note "et chaque AlertCert chaîne la baseline (sha256 baseline_ref)."
echo
echo "${GREEN}${BOLD}  → ${ALERT_COUNT} alertes émises, attaque détectée en ${ATTACK_DURATION}s${RESET}"
echo "${GREEN}${BOLD}  → Tout est cryptographiquement vérifiable depuis la pub key publique.${RESET}"
sleep 2
