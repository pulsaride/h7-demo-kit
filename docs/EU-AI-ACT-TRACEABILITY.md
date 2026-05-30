# Traçabilité H7 → Exigences EU AI Act (Août 2026)

**Version** : 1.0  
**Date** : 2026-05-24  
**Scope** : Mapping technique des artefacts H7 vers les obligations de transparence
et de surveillance de l'EU AI Act (Règlement (UE) 2024/1689) applicables
aux systèmes à haut risque (Annexe III).

---

## 1. Positionnement H7 dans le cadre EU AI Act

Pulsaride H7 est un **système de surveillance comportementale** des processus
système. Il s'intègre dans la chaîne de conformité EU AI Act à deux titres :

1. **Outil de monitoring** d'un système IA à haut risque déployé chez le client :
   H7 assure la surveillance continue de la dérive comportementale du runtime
   IA (Annexe III, catégories 1, 2, 5, 6, 7).

2. **Composant audit-ready** : les artefacts H7 (`.cal`, `NDJSON`, rapports
   signés) constituent des preuves techniques opposables pour les organismes
   notifiés (Notified Bodies) et les autorités compétentes.

---

## 2. Mapping champ `.cal` → obligations EU AI Act

| Champ `.cal` / NDJSON | Obligation EU AI Act | Article / Considérant | Preuve fournie |
|---|---|---|---|
| `kappa` (KL-divergence comportementale) | Surveillance continue des performances | Art. 9 §7, Art. 72 | Métrique quantitative de dérive comportementale |
| `cusum_s` / `h` (accumulation CUSUM) | Détection de changement de comportement | Art. 9 §7 | Détecteur statistique calibré, seuil opposable |
| `ts_iso` / `ts_ns` (horodatage) | Traçabilité temporelle des événements | Art. 12 §1 | Horodatage UTC nanoseconde, complété par TSR RFC 3161 |
| `sig_b64` (signature Ed25519) | Intégrité et authenticité des logs | Art. 12 §1, §2 | Signature cryptographique tamper-evident |
| `alert_cert_path` → `.cal` sidecar | Log events liés à la sécurité | Art. 12 §1 | Lien vers le sidecar signé de l'alerte |
| `baseline_sha256_hex` (dans `.cal`) | Référentiel de comportement normal | Art. 9 §1, §2 | Hash cryptographique de la baseline calibrée |
| `host` / `agent_id` | Identification de l'entité surveillée | Art. 12 §1 | Identifiant unique de l'agent |
| `severity` (INFO/WARN/CRITICAL) | Niveaux d'alerte et escalade | Art. 9 §4 | Classification normalisée des événements |
| `shadow_mode` | Mode supervision vs détection active | Art. 9 §3 | Flag explicite du mode opérationnel |
| `calibration_source` (`.cal` baseline) | Documentation du processus de calibration | Art. 9 §1, Annexe IV §3 | Distingue calibration live vs fallback fixture |

---

## 3. Chaîne de traçabilité complète

```
Observation kernel (eBPF sched_switch)
    │
    ▼
Métrique κ + CUSUM  ──→  alert-NNNNNN.cal  (Ed25519 signé)
    │                        │
    │                        ├── baseline_sha256_hex  → baseline.json (calibrée)
    │                        ├── ts_iso / ts_ns       → TSR RFC 3161 (optionnel)
    │                        └── sig_b64              → vérifiable offline
    │
    ▼
alerts.ndjson (NDJSON stream)
    │
    ▼
drift-report-*.json  (Ed25519 signé)  ──→ verdict NOMINAL / DRIFT_DETECTED
    │
    ▼
audit-package/  (MANIFEST.json + SHA-256 de chaque artefact)
    │
    ├── Organisme notifié (Notified Body)
    ├── Autorité de surveillance du marché (Art. 74)
    └── Documentation technique (Art. 11, Annexe IV)
```

---

## 4. Obligations couvertes article par article

### Art. 9 — Système de gestion des risques

| Sous-obligation | Couvert par H7 | Artefact |
|---|---|---|
| §1 — Processus de gestion des risques continu | ✓ | Alertes en continu + drift reports |
| §2 — Identification et analyse des risques | ✓ | `severity`, `cusum_s > h` |
| §4 — Mesures de gestion des risques | ✓ | Seuil `h`, `k_slack`, shadow mode |
| §7 — Surveillance post-déploiement | ✓ | `sim-live-telemetry.py`, stream WS |

### Art. 11 — Documentation technique

| Sous-obligation | Couvert par H7 | Artefact |
|---|---|---|
| Annexe IV §3 — Description des mesures de surveillance | ✓ | `SKILL.md`, `RUNBOOK.md` |
| Annexe IV §4 — Mesures de sécurité | ✓ | Auth Bearer, CORS restreint, garde path traversal |
| Annexe IV §5 — Description des performances et métriques | ✓ | `drift-report-*.json` |

### Art. 12 — Tenue des registres (logging)

| Sous-obligation | Couvert par H7 | Artefact |
|---|---|---|
| §1 — Capacité de journalisation automatique | ✓ | `alerts.ndjson` (NDJSON append-only) |
| §1 — Période de journalisation suffisante | ✓ | Fichier cumulatif, archivage `.cal` sidecars |
| §2 — Intégrité des logs | ✓ | Signature Ed25519 par alerte, `MANIFEST.json` |
| §3 — Accessibilité des logs aux autorités | ✓ | `gen-audit-package.py` → bundle autonome |

### Art. 72 — Surveillance post-marché

| Sous-obligation | Couvert par H7 | Artefact |
|---|---|---|
| Collecte et analyse de données en conditions réelles | ✓ | `alerts.ndjson` + `kappa`, `cusum_s` |
| Rapport périodique aux autorités | ✓ | `drift-report-*.json` (génération automatisée) |
| Détection d'incidents sérieux | ✓ | `severity: CRITICAL` + alertes BREACH |

---

## 5. Points de conformité non couverts par H7 seul

Ces obligations incombent au déployeur / fournisseur du système IA :

| Obligation | Article | Note pour déployeur |
|---|---|---|
| Enregistrement dans la base EU IA (Art. 71) | Art. 71 | H7 fournit les métadonnées techniques nécessaires |
| Déclaration de conformité UE | Art. 47 | H7 fournit les preuves techniques (audit-package) |
| Notification des incidents sérieux (72h) | Art. 73 | H7 détecte (`severity: CRITICAL`) ; la notification reste du ressort du déployeur |
| Évaluation de la conformité avant mise sur le marché | Art. 43 | H7 fournit documentation et preuves pour le Notified Body |
| Horodatage qualifié eIDAS | Art. 12 §3 (si applicable) | Utiliser DigiCert TSA qualifiée via `ts-request.py --digicert` |

---

## 6. Checklist de traçabilité pour audit Notified Body

```
[ ] alerts.ndjson archivé et intègre (SHA-256 dans MANIFEST.json)
[ ] Chaque alerte CRITICAL a un .cal sidecar signé
[ ] baseline.json non-pending (sha256 présent, calibration_source documenté)
[ ] drift-report-*.json généré pour la période auditée (sig_b64 valide)
[ ] TSR RFC 3161 disponibles sur les certs critiques (.tsr.freetsa)
[ ] CRL vérifiée et non-expirée (validate-crl.py exit 0)
[ ] audit-package/ généré et transmis à l'organisme notifié
[ ] RUNBOOK.md + SKILL.md fournis comme documentation opérationnelle
```
