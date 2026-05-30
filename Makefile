# h7-demo-kit — Makefile (cibles 8 min de démo)
# PLAN-STRATEGIQUE-v2 §4.1 livrable T5.

SHELL := /bin/bash
.ONESHELL:

# Prefer venv/bin/pytest when a local virtualenv exists, fall back to system pytest.
PYTEST := $(shell \
  if   [ -x "$(CURDIR)/venv/bin/pytest"  ]; then echo "$(CURDIR)/venv/bin/pytest"; \
  elif [ -x "$(CURDIR)/.venv/bin/pytest" ]; then echo "$(CURDIR)/.venv/bin/pytest"; \
  else echo pytest; fi)

RUN_DIR      := $(CURDIR)/run
BIN_DIR      := $(RUN_DIR)/bin
KEYS_DIR     := $(RUN_DIR)/keys
LOGS_DIR     := $(RUN_DIR)/logs
ALERTS_DIR   := $(RUN_DIR)/alerts
BASELINE     := $(RUN_DIR)/baseline.json
DEMO_CFG     := $(RUN_DIR)/h7-demo.toml
PID_SENSOR   := $(RUN_DIR)/sensor.pid
PID_SINK     := $(RUN_DIR)/sinkhole.pid

SENSOR_BIN   := $(BIN_DIR)/h7-sensor
H7_BIN       := $(BIN_DIR)/h7
SINKHOLE     := scripts/demo-sinkhole.py
FETCH_BIN    := scripts/fetch-release-binaries.sh

H7_RELEASE_REPO ?= pulsaride/h7-demo-kit
H7_RELEASE_TAG  ?= latest

# Verbosité sensor. "warn" en prod (~0 ligne/s, alertes seulement),
# "info" en mode démo (~10 lignes/s, affichage tick par tick).
# Surcharger : make up LOG_LEVEL=info, ou : make demo-mode up
LOG_LEVEL ?= warn

.PHONY: help check setup fetch-binaries calibrate up attack attack-vercel verify verify-baseline verify-alert verify-schema down clean status mirror-release reset-alerts watch demo-mode stream-test-telemetry stream-telemetry verify-gate-hardening seed-offline-baseline test-btf-fallback test-kernel-heterogeneous gen-audit-package gen-crl validate-crl ts-harvest gen-drift-report demo-kit-export e2e-full compliance-bundle verify-attest test dev-setup

help:
	@echo "Cibles : check fetch-binaries setup calibrate up attack attack-vercel verify-baseline verify-alert verify down clean status reset-alerts watch demo-mode stream-test-telemetry verify-gate-hardening"
	@echo ""
	@echo "Première utilisation (calibration ~2 min) :"
	@echo "  1. make setup          # télécharge binaires + clés + config TOML -> run/"
	@echo "  2. make calibrate      # calibre la baseline sur cette machine (2 min, sudo)"
	@echo ""
	@echo "Séquence démo (~5 min) :"
	@echo "  3. make up             # sensor + sinkhole en background (sudo)"
	@echo "  4. make attack         # déclenche le worker bruyant 60s (profil générique)"
	@echo "     make attack-vercel  # variante : pattern pivot supply-chain Vercel 2026-04-21"
	@echo "  5. make verify-alert   # vérifie crypto de toutes les alertes"
	@echo "  6. make down           # arrêt propre + purge logs/sensor (alertes conservées)"
	@echo ""
	@echo "Opérations :"
	@echo "  make watch             # tail -F alerts.ndjson (seulement les alertes)"
	@echo "  make reset-alerts      # vide run/alerts/ + alerts.ndjson (conserve clés/baseline/binaires)"
	@echo "  make demo-mode         # régénère la config avec log_level=info (affichage tick/tick)"
	@echo ""
	@echo "Variables optionnelles :"
	@echo "  H7_RELEASE_REPO=$(H7_RELEASE_REPO)"
	@echo "  H7_RELEASE_TAG=$(H7_RELEASE_TAG)"
	@echo "  LOG_LEVEL=$(LOG_LEVEL)   # error|warn|info|debug|trace (défaut: warn)"

check:
	@command -v python3 >/dev/null || { echo "python3 manquant"; exit 1; }
	@command -v curl >/dev/null    || { echo "curl manquant"; exit 1; }
	@command -v openssl >/dev/null || { echo "openssl manquant"; exit 1; }
	@command -v jq >/dev/null      || { echo "jq manquant (sudo apt install jq)"; exit 1; }
	@test -x "$(SENSOR_BIN)"       || { echo "$(SENSOR_BIN) absent — lancer make fetch-binaries"; exit 1; }
	@test -x "$(H7_BIN)"           || { echo "$(H7_BIN) absent — lancer make fetch-binaries"; exit 1; }
	@test -f "$(SINKHOLE)"         || { echo "$(SINKHOLE) absent"; exit 1; }
	@echo "✓ tous les pré-requis présents"

fetch-binaries:
	mkdir -p "$(BIN_DIR)"
	@echo "-> téléchargement des binaires depuis GitHub Releases"
	H7_RELEASE_REPO="$(H7_RELEASE_REPO)" H7_RELEASE_TAG="$(H7_RELEASE_TAG)" \
		bash "$(FETCH_BIN)" "$(BIN_DIR)"

setup: fetch-binaries
	mkdir -p "$(KEYS_DIR)" "$(LOGS_DIR)" "$(ALERTS_DIR)"
	@if [ ! -f "$(KEYS_DIR)/h7-cert-issuer.sec" ]; then
		echo "-> génération clés Ed25519 dans $(KEYS_DIR)/"
		openssl genpkey -algorithm Ed25519 -out "$(KEYS_DIR)/h7-cert-issuer.sec" >/dev/null 2>&1
		chmod 600 "$(KEYS_DIR)/h7-cert-issuer.sec"
		openssl pkey -in "$(KEYS_DIR)/h7-cert-issuer.sec" -pubout -out "$(KEYS_DIR)/h7-cert-issuer.pub" >/dev/null 2>&1
		openssl pkey -in "$(KEYS_DIR)/h7-cert-issuer.sec" -pubout -outform DER | sha256sum | awk '{print "h7-cert-issuer-v1\nfingerprint-sha256: "$$1}' > "$(KEYS_DIR)/h7-cert-issuer.id"
	else
		echo "✓ clés déjà présentes ($(KEYS_DIR)/)"
	fi
	@echo "-> génération config démo $(DEMO_CFG) (log_level=$(LOG_LEVEL))"
	python3 scripts/gen-demo-cfg.py \
		--run-dir   "$(RUN_DIR)" \
		--keys-dir  "$(KEYS_DIR)" \
		--logs-dir  "$(LOGS_DIR)" \
		--baseline  "$(BASELINE)" \
		--log-level "$(LOG_LEVEL)" \
		--out       "$(DEMO_CFG)"
	@echo "✓ setup terminé. Prochain : make calibrate (2 min, sudo requis)"

calibrate: setup
	@if [ -f "$(BASELINE)" ] && python3 -c "import json,sys; d=json.load(open('$(BASELINE)')); sys.exit(0 if d.get('sha256','pending') != 'pending' else 1)" 2>/dev/null; then
		echo "✓ baseline déjà calibrée — supprimer $(BASELINE) pour recalibrer"
	elif [ ! -r /sys/kernel/btf/vmlinux ]; then
		echo "[!] /sys/kernel/btf/vmlinux absent — bascule en baseline offline-fallback (pinned fixture)"
		$(MAKE) --no-print-directory seed-offline-baseline
	else
		echo "-> calibration de la baseline (~2 min, sudo requis)"
		echo "   Le sensor observe sched_switch en Phase Alpha sur cette machine."
		sudo "$(SENSOR_BIN)" \
			--mode calibrate \
			--duration 120 \
			--output "$(BASELINE)" \
			--config "$(DEMO_CFG)"
		echo "✓ baseline écrite : $(BASELINE)"
	fi

seed-offline-baseline: ## Seed run/baseline.json from pinned fixture when BTF is unavailable (no network)
	@python3 scripts/seed-offline-baseline.py \
		--fixture fixtures/baseline.example.json \
		--output  "$(BASELINE)"

up: setup
	@if [ ! -f "$(BASELINE)" ]; then
		echo "[ERREUR] Baseline absente. Lancer d'abord : make calibrate"
		exit 1
	fi
	@if python3 -c "import json,sys; d=json.load(open('$(BASELINE)')); sys.exit(0 if d.get('sha256','pending') == 'pending' else 1)" 2>/dev/null; then
		echo "[ERREUR] Baseline non calibrée (sha256=pending). Lancer : make calibrate"
		exit 1
	fi
	@echo "-> lancement sinkhole loopback (127.0.0.1:9999)"
	@# Pre-check : port 9999 doit être libre. Sinon le sinkhole crashe EADDRINUSE
	@# silencieusement et toute la démo part dans le décor (cf. incident 2026-05-22).
	@if ss -ltn 2>/dev/null | awk '{print $$4}' | grep -qE '(127\.0\.0\.1|0\.0\.0\.0|\*):9999$$'; then \
		echo "[ERREUR] Port 9999 déjà occupé. Sinkhole zombie d'une session précédente ?"; \
		echo "         Diagnostique : ss -ltnp | grep :9999"; \
		echo "         Nettoyage    : kill <pid_orphelin> puis relancer make up"; \
		exit 1; \
	fi
	nohup python3 "$(SINKHOLE)" --log "$(LOGS_DIR)/sinkhole.ndjson" \
		>"$(LOGS_DIR)/sinkhole.stderr" 2>&1 &
	echo $$! > "$(PID_SINK)"
	sleep 0.5
	@# Vérifie que le sinkhole est vivant ET écoute. Sinon : abort, ne lance pas le sensor.
	@if ! kill -0 $$(cat "$(PID_SINK)") 2>/dev/null; then \
		echo "[ERREUR] sinkhole mort au démarrage. Voir $(LOGS_DIR)/sinkhole.stderr"; \
		tail -5 "$(LOGS_DIR)/sinkhole.stderr" 2>/dev/null | sed 's/^/  | /'; \
		rm -f "$(PID_SINK)"; \
		exit 1; \
	fi
	@if ! python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1',9999))==0 else 1)"; then \
		echo "[ERREUR] sinkhole vivant mais n'écoute pas sur 127.0.0.1:9999. Voir $(LOGS_DIR)/sinkhole.stderr"; \
		tail -5 "$(LOGS_DIR)/sinkhole.stderr" 2>/dev/null | sed 's/^/  | /'; \
		kill $$(cat "$(PID_SINK)") 2>/dev/null || true; \
		rm -f "$(PID_SINK)"; \
		exit 1; \
	fi
	@echo "   sinkhole pid=$$(cat $(PID_SINK)) (vérifié : écoute 127.0.0.1:9999)"
	@echo "-> lancement h7-sensor (mode monitor, shadow_mode=false, RUST_LOG=$(LOG_LEVEL))"
	sudo RUST_LOG=$(LOG_LEVEL) nohup "$(SENSOR_BIN)" \
		--config "$(DEMO_CFG)" \
		>"$(LOGS_DIR)/sensor.stdout" 2>"$(LOGS_DIR)/sensor.stderr" &
	echo $$! > "$(PID_SENSOR)"
	sleep 1
	@echo "✓ sensor pid=$$(cat $(PID_SENSOR))"
	@echo "   alertes en direct : make watch    (suit run/logs/alerts.ndjson)"
	@echo "   logs sensor bruts : tail -f $(LOGS_DIR)/sensor.stderr"

attack:
	@echo "-> génération de bruit sched_switch (60s, 4 workers)"
	python3 scripts/attack-noise.py --duration 60 --workers 4 \
		--beacon-url http://127.0.0.1:9999/exfil

attack-vercel:
	@echo "[*] Triggering Vercel-pattern supply-chain attack simulation (2026-04-21)"
	@if [ ! -f "$(PID_SINK)" ] || ! kill -0 $$(cat "$(PID_SINK)") 2>/dev/null; then \
		echo "[ERREUR] sinkhole loopback absent. Lancer d'abord : make up"; \
		exit 1; \
	fi
	@if ! python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.5); sys.exit(0 if s.connect_ex(('127.0.0.1',9999))==0 else 1)"; then \
		echo "[ERREUR] 127.0.0.1:9999 inaccessible. Sinkhole non prêt."; \
		exit 1; \
	fi
	python3 scripts/attack-noise.py --vercel-pattern --duration 60 --workers 4 \
		--beacon-url http://127.0.0.1:9999/exfil
	@echo "[+] Scénario Vercel exécuté. Lancer 'make verify' pour valider l'AlertCert."

verify-baseline:
	@echo "-> vérification cryptographique de la baseline"
	@"$(H7_BIN)" cal verify "$(BASELINE)" --public-key "$(KEYS_DIR)/h7-cert-issuer.pub"

verify-alert:
	@echo "-> vérification cryptographique de toutes les alertes émises"
	@H7_BIN="$(H7_BIN)" \
		bash scripts/verify-loop.sh "$(ALERTS_DIR)" "$(KEYS_DIR)/h7-cert-issuer.pub" "$(BASELINE)"

verify-schema:
	@echo "-> validation schéma alerts.ndjson (docs/schemas/alert-v1.1.json)"
	@python3 scripts/validate-alerts-ndjson.py "$(LOGS_DIR)/alerts.ndjson"

verify: verify-alert verify-schema

down:
	@if [ -f "$(PID_SENSOR)" ]; then
		echo "-> stop sensor pid=$$(cat $(PID_SENSOR))"
		sudo kill $$(cat "$(PID_SENSOR)") 2>/dev/null || true
		rm -f "$(PID_SENSOR)"
	fi
	@if [ -f "$(PID_SINK)" ]; then
		echo "-> stop sinkhole pid=$$(cat $(PID_SINK))"
		kill $$(cat "$(PID_SINK)") 2>/dev/null || true
		rm -f "$(PID_SINK)"
	fi
	@# Purge logs bruts (bornage disque) : on garde alerts.ndjson + run/alerts/*.cal (preuves).
	@: > "$(LOGS_DIR)/sensor.stdout" 2>/dev/null || true
	@: > "$(LOGS_DIR)/sensor.stderr" 2>/dev/null || true
	@: > "$(LOGS_DIR)/sinkhole.stderr" 2>/dev/null || true
	@echo "✓ arrêt propre (logs sensor purgés ; alertes conservées)"

reset-alerts:
	@rm -f "$(ALERTS_DIR)"/alert-*.cal
	@: > "$(LOGS_DIR)/alerts.ndjson" 2>/dev/null || true
	@echo "✓ alertes purgées ($(ALERTS_DIR)/ + alerts.ndjson) ; clés/baseline/binaires conservés"

watch:
	@test -d "$(LOGS_DIR)" || { echo "[ERREUR] $(LOGS_DIR) absent. Lancer make up d'abord."; exit 1; }
	@touch "$(LOGS_DIR)/alerts.ndjson"
	@echo "-> tail -F $(LOGS_DIR)/alerts.ndjson  (Ctrl+C pour quitter)"
	@tail -F "$(LOGS_DIR)/alerts.ndjson"

demo-mode:
	@echo "-> mode démo : régénération config avec log_level=info"
	@$(MAKE) --no-print-directory setup LOG_LEVEL=info
	@echo "✓ prochain make up tournera en verbose (info). Pour repasser en prod : make setup"

clean: down
	rm -rf "$(LOGS_DIR)" "$(ALERTS_DIR)"
	rm -f "$(BASELINE)" "$(DEMO_CFG)"
	@echo "✓ logs/alertes/baseline purgés (clés et binaires conservés dans run/)"

status:
	@echo "─── état démo ───"
	@if [ -f "$(PID_SENSOR)" ] && kill -0 $$(cat "$(PID_SENSOR)") 2>/dev/null; then
		echo "sensor    : up (pid $$(cat $(PID_SENSOR)))"
	else
		echo "sensor    : down"
	fi
	@if [ -f "$(PID_SINK)" ] && kill -0 $$(cat "$(PID_SINK)") 2>/dev/null; then
		echo "sinkhole  : up (pid $$(cat $(PID_SINK)))"
	else
		echo "sinkhole  : down"
	fi
	@echo "alertes   : $$(ls $(ALERTS_DIR) 2>/dev/null | wc -l) sidecar(s) .cal"
	@echo "ndjson    : $$(wc -l < $(LOGS_DIR)/alerts.ndjson 2>/dev/null || echo 0) ligne(s)"

stream-test-telemetry: ## Append continuous simulated kappa metrics to the live NDJSON file for UI verification
	@echo "[*] Initializing live telemetry stream into run/logs/alerts.ndjson..."
	@python3 scripts/sim-live-telemetry.py

stream-telemetry: ## Stream NDJSON telemetry to the path the docker compose monitor reads (run/alerts/alerts.ndjson)
	@mkdir -p run/alerts
	@echo "[*] Streaming NDJSON to run/alerts/alerts.ndjson (Ctrl-C to stop)"
	python3 scripts/sim-live-telemetry.py \
		--output run/alerts/alerts.ndjson \
		--interval-ms 500

test-btf-fallback: ## Validate the offline baseline fallback path (no kernel/BTF required)
	@echo "[*] Running BTF-fallback regression test"
	@python3 scripts/test-btf-fallback.py

test-kernel-heterogeneous: ## Non-regression test across heterogeneous kernel scenarios (BTF + offline)
	@echo "[*] Running heterogeneous-kernel non-regression suite"
	@python3 scripts/test-kernel-heterogeneous.py

gen-audit-package: ## Bundle a signed audit evidence package for client pilot (output: run/audit-package/)
	@echo "[*] Generating audit evidence package in run/audit-package/"
	@python3 scripts/gen-audit-package.py \
		--alerts-ndjson "$(LOGS_DIR)/alerts.ndjson" \
		--alerts-dir    "$(ALERTS_DIR)" \
		--baseline      "$(BASELINE)" \
		--pub-key       "$(KEYS_DIR)/h7-cert-issuer.pub" \
		--output-dir    "$(RUN_DIR)/audit-package"

gen-crl: ## Generate / refresh the Ed25519-signed CRL (h7-cal/crl/v1, ADR-PROD-008)
	@python3 scripts/gen-crl.py --keys-dir "$(KEYS_DIR)" --out "$(RUN_DIR)/crl.json"

validate-crl: ## Validate the local CRL signature and expiry
	@python3 scripts/validate-crl.py \
		--crl "$(RUN_DIR)/crl.json" \
		--pub-key "$(KEYS_DIR)/h7-crl-signer.pub"

ts-harvest: ## Batch-timestamp recent .cal files via FreeTSA (RFC 3161, ADR-PROD-009)
	@python3 scripts/ts-request.py --harvest "$(ALERTS_DIR)" --since-minutes 60

demo-kit-export: ## Package a client-ready export bundle (no run/ state, pre-seeded baseline)
	@bash scripts/demo-kit-export.sh

gen-drift-report: ## Generate a signed non-drift report (last 24h) for compliance
	@python3 scripts/gen-drift-report.py \
		--alerts-ndjson "$(LOGS_DIR)/alerts.ndjson" \
		--baseline      "$(BASELINE)" \
		--keys-dir      "$(KEYS_DIR)" \
		--output-dir    "$(RUN_DIR)/reports"

verify-gate-hardening: ## Run security regression suite against the h7-monitor FastAPI gateway
	@echo "[*] Running gateway hardening regression suite"
	@H7_MONITOR_BACKEND_DIR="$${H7_MONITOR_BACKEND_DIR:-$(CURDIR)/../../h7-monitor/backend}" \
		python3 scripts/verify-gate-hardening.py

e2e-full: ## Full pipeline smoke test without kernel sensor (sim → monitor → verify → drift → audit)
	@echo "[*] Running full e2e pipeline (no eBPF required)"
	@H7_MONITOR_BACKEND_DIR="$${H7_MONITOR_BACKEND_DIR:-$(CURDIR)/../../h7-monitor/backend}" \
	H7_ATTEST_TOKEN="$${H7_ATTEST_TOKEN:-h7-e2e-test-token}" \
		bash scripts/e2e-full.sh

compliance-bundle: gen-drift-report ts-harvest ## Generate and timestamp compliance artefacts in one shot
	@echo "✓ compliance-bundle complete (drift report + RFC 3161 timestamps)"

dev-setup: ## Create venv/ and install test dependencies (run once after cloning)
	@if [ ! -d venv ]; then \
		echo "[dev-setup] creating venv/ …"; \
		python3 -m venv venv; \
	else \
		echo "[dev-setup] venv/ already exists — skipping creation"; \
	fi
	venv/bin/pip install --quiet -r requirements-test.txt
	@echo "✓ dev-setup complete — run: make test"

test: ## Run the pytest unit/integration suite (no eBPF, no network, no binaries required)
	@if [ "$(PYTEST)" = "pytest" ] && ! command -v pytest >/dev/null 2>&1; then \
		echo "[test] pytest not found. Run first:  make dev-setup"; \
		exit 1; \
	fi
	$(PYTEST) tests/ -v

verify-attest: ## Offline-verify a downloaded .cbor attestation envelope
	@if [ -z "$(CBOR)" ]; then \
		echo "Usage: make verify-attest CBOR=path/to/attestation.cbor [PUBKEY=<hex>]"; \
		exit 2; \
	fi
	@bash scripts/verify-attest.sh "$(CBOR)" "$(PUBKEY)"

# Mirror a signed Release from the private upstream repo (pulsaride/p-h7) to
# this public h7-demo-kit Releases. Maintainer-only target.
# Usage:  make mirror-release TAG=v0.7.2
mirror-release:
	@if [ -z "$(TAG)" ]; then \
		echo "usage: make mirror-release TAG=vX.Y.Z"; \
		exit 2; \
	fi
	bash scripts/mirror-release.sh "$(TAG)"
