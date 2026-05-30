#!/usr/bin/env bash
# tamper-alert.sh — corrompt 1 octet d'un .cal pour démontrer le rejet.
# PLAN-STRATEGIQUE-v2 §4.1 livrable T5 (démo tamper-evident, gap N6).
# Usage : tamper-alert.sh <fichier.cal>

set -euo pipefail

CERT="${1:?usage: $0 <fichier.cal>}"

if [[ ! -f "$CERT" ]]; then
    echo "✗ fichier introuvable : $CERT" >&2
    exit 2
fi

CP="${CERT}.tampered.cal"
cp "$CERT" "$CP"

# Cible : le champ kappa_observed (présent dans tous les AlertCert), on
# remplace le premier '0' du body par '9'. Casse forcément la sig.
python3 - "$CP" <<'PY'
import json, sys
p = sys.argv[1]
with open(p) as f:
    cert = json.load(f)
# bump kappa_observed pour casser body_sha256 + signature
cert["body"]["params"]["kappa_observed"] += 0.0001
with open(p, "w") as f:
    json.dump(cert, f, indent=2)
print(f"[tamper] kappa_observed bumped dans {p}")
PY

echo ""
echo "→ tente la vérification du fichier corrompu :"
echo "  h7 cal verify-alert $CP --public-key <pubkey>"
echo ""
echo "Sortie attendue : ✗ INVALIDE (signature ou body_sha256 mismatch)"
