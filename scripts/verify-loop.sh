#!/usr/bin/env bash
# verify-loop.sh — vérifie crypto + binding baseline de tous les .cal d'alerte.
# PLAN-STRATEGIQUE-v2 §4.1 livrable T5.
# Usage : verify-loop.sh <alerts_dir> <pubkey_pem> <baseline.json>

set -euo pipefail

ALERTS_DIR="${1:?usage: $0 <alerts_dir> <pubkey_pem> <baseline.json>}"
PUBKEY="${2:?clé publique PEM requise}"
BASELINE="${3:?baseline.json requise pour le binding}"

H7_BIN="${H7_BIN:-}"

if [[ -z "$H7_BIN" ]]; then
    echo "✗ H7_BIN non défini. Exporter H7_BIN ou lancer via Makefile (make verify-alert)." >&2
    exit 2
fi

if [[ ! -x "$H7_BIN" ]]; then
    echo "✗ binaire h7 introuvable : $H7_BIN" >&2
    exit 2
fi
if [[ ! -d "$ALERTS_DIR" ]]; then
    echo "✗ dossier alertes introuvable : $ALERTS_DIR" >&2
    exit 2
fi

# Extrait le sha256 self-référencé de la baseline.
BASELINE_SHA=$(jq -r .sha256 "$BASELINE")
if [[ -z "$BASELINE_SHA" || "$BASELINE_SHA" == "null" ]]; then
    echo "✗ baseline sans champ sha256 : $BASELINE" >&2
    exit 2
fi

shopt -s nullglob
files=("$ALERTS_DIR"/alert-*.cal)
if [[ ${#files[@]} -eq 0 ]]; then
    echo "ℹ aucune alerte à vérifier dans $ALERTS_DIR (rien n'a déclenché CUSUM ?)"
    exit 0
fi

ok=0
fail=0
for f in "${files[@]}"; do
    if "$H7_BIN" cal verify-alert "$f" \
        --public-key "$PUBKEY" \
        --baseline-sha256 "$BASELINE_SHA" >/dev/null 2>&1; then
        echo "✓ $(basename "$f")"
        ok=$((ok + 1))
    else
        echo "✗ $(basename "$f") — REJETÉ"
        fail=$((fail + 1))
    fi
done

echo ""
echo "─── récap ───"
echo "OK      : $ok"
echo "REJETÉS : $fail"
echo "baseline_sha256 (binding) : $BASELINE_SHA"
[[ $fail -eq 0 ]]
