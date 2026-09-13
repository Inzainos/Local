## 2026-09-13 ? H2/H3/H4 classify (Agente-C)
- Nested ONNX ?canon ? `_archive/20260913/models_nested/`; loki nested id?ntico borrado
- Baks/hex obsolete borrados; schema tar ? `_archive/20260913/schema/`
- Symlink venv/streamlit eliminado

## 2026-09-13 ? Auditor?a GitHub (Agente-C)

- Doc: `docs/AUDIT_GITHUB_20260913.md` (H1?H6 + decisiones pendientes).
- Push `Inzainos/Local` rama `local/sentinel-omega`: cero secretos; remediaci?n H1?H4/H6 en hold hasta GO Capit?n.

## 2026-09-13 — Duelo launcher cerrado, watchdog/ops, Schumann/Alfa2 tests

- **Fixed:** `sentinel-omega-scheduler` disabled — dejaba de matar al launcher de `sentinel-omega` (alertas Telegram desbloqueadas). Watchdog ya no re-enable el scheduler.
- **Ops:** dashboard Sentinel `:8510` active; Ollama = Windows `ollama.exe` (unit Kali disabled); backup offbox catch-up `watchdog_2026-09-13_1253.tar.gz` (hueco 12-sep irrecuperable).
- **Tests:** Schumann connector tests alineados a ingest None (6/6); `pytrends` en venv; Alfa2 7 passed (Agente-T).
- **Docs:** `docs/SESSION_2026-09-13.md`, `docs/SYSTEM_HEALTH_2026-09-13.md`.

## 2026-09-10/11 — Dashboard 6 tabs, ingest Schumann/Delta, ONNX retrain

- Dashboard React: exactamente 6 tabs; APIs RO schumann_vivo/delta/clima_espacial; promovido Dev→Test→Prod.
- Telegram messaging: eliminado copy "lotería" de alertas/digest.
- Ingest: WPC Tomsk (linaje Drive extractor_vision_schumann); sin fallback falso 7.83/0; Schumann vivo 8.26/21.46; clima 2026 gapfill; sismos refetch; Delta no escribe all-zero.
- ONNX: wipe+retrain; Prod deja bootstrap-only y gana Loki.
- Docs: SESSION_2026-09-10.md, SYSTEM_HEALTH, INGEST_FIX, TRAIN_RESTART, DASHBOARD_6TABS_DONE.
- No corrido: launcher --entrenar firmas.

# Changelog - Sentinel Omega

## [Unreleased] - 2026-09-10 - Dashboard 6 tabs → Prod + lottery scrub + health/ingest docs

### Changed
- Promocion Dev→Prod (flat + nested) del dashboard React 6 tabs + api.py/README/package.json (puerto 5174).
- Messaging loteria scrub (0 matches en Prod); restart ~18:06 CST.
- Docs: SYSTEM_HEALTH_2026-09-10.md, DASHBOARD_6TABS_DONE.md, INGEST_FIX_2026-09-10.md stub (pending).

### Notes
- Health OK. DB empty/flat (correlaciones vacias / frescura) documentado; DB file no escrita en esta pasada.
- Blockers: correlaciones vacias, ONNX placeholder, tsc shim, prod gate firmas, ingest PENDING.
- NO se habilito entrenar/firmas/remapeo. Streamlit 8501 legacy sin tocar.

---


## [2.5.4] - 2026-09-04 - Fixes: Vite/Health/Telegram — documentado

### Fixed
- **Vite dev WSL→Windows (ERR_CONNECTION_REFUSED)**:  host  aislado de WSL no ruteaba a Windows. Fix:  +  en  local (gitignored). Verificado Microsoft Windows [Versi¢n 10.0.26340.9233]
(c) Microsoft Corporation. Todos los derechos reservados.

C:\Windows\System32> y  ambos 200 desde Windows.  también en  con CORS para 5173/5174.
- **Dashboard DB desconectada (falso negativo)**: frontend esperaba  pero  devolvía  sin wrapper. KPI "DB Conectada" salía No/rojo aunque DB 834M/11259 ciclos estaba OK. Fix:  ahora envuelve  →  vía . Verificado .
- **Launcher crash loop **:  importaba  solo dentro de , pero lo usaba fuera. Cada ciclo (211s) fallaba. Fix:  arriba de , pycache limpiado.
- **Servicios colgados**:  stale 1 día (duplicado) y  15h 98% CPU → /.

### Added
- **Build prod estático**:  1.01s 63 módulos 282KB/85KB gzip  como fallback sin depender de vite dev.

### Docs
- README sección Dashboard dev/troubleshooting, CLAUDE arquitectura dashboard, este CHANGELOG.

## [2.5.4] - 2026-09-04 - Compat Layer + API/React + Health

### Added
- **FastAPI compat layer** (): 13 alias sin prefijo  para el frontend React (, , , , , , ) — resuelven contra  reales con fallback sintético; verificados 13/13 con  (200).
- **Dependencias API**: , ,  en .
- **Dashboard React** (): 6 tabs (Principal/Telemetría/Consenso/Análisis/Agentes/Sistema),  63 módulos 282KB/85KB gzip.

### Fixed
- **Health DB path**:  symlink a  para que  resuelva  desde layout nested.
- **Imports dual-layout**:  y  sincronizados flat↔nested; Obtaining file:///C:/WINDOWS/system32 reinstalado.

### Changed
- **Versión**:  2.5.0 → 2.5.4.
- **Docs**:  (dashboard React 6 tabs + Streamlit 11 legacy, 8 agentes),  (8 agentes).

---

## [Unreleased] - 2026-09-04 - The Third Act: Loki & SNT Evolution

### Added
- **Loki Agent (Act 3)**: Implementation of the Unified Field Theory (Fractal-Bayesian).
  - Logic: Gauss-Jordan Cleaning -> Fourier Frequency Scan -> Bayesian Probability Update.
  - Base Node: Tlaxcala, Mexico.
- **SNT Evolution**:
  - **Delta (Financial)**: Removed WATCH ceiling. Delta now emits ALERT for extreme financial stress.
  - **Beta-1 (The Artist)**: Reprogrammed to generate "Cymatic Figures" (system vibration snapshots).
  - **Beta-2 (The Analyst)**: Reprogrammed to interpret figures, search for historical replicas by magnitude, and weigh against atmospheric stress.
  - **Alfa-2 (Satellite)**: ELIMINATED LIVE TRAINING. Now forces use of historical baseline to prevent adaptation to cycle noise.
- **Consensus Hierarchy**: Updated pipeline to SNT -> Omega -> Loki.
- **AGENTS.md**: Created the formal registry of agent roles and the consensus ladder.

### Changed
- **Consensus Logic**: The Father now acts as a tiered validator across the three acts.
- **Alfa-2**: Transitioned from online learning to historical baseline deviation analysis.

---

## [Unreleased] - 2026-09-04 - Consensus Hierarchy & Juez Law

### Changed
- **Padre Agent (GeodynamicPadre)**: Implemented Three-Act Consensus Hierarchy.
  - Act 1: SNT Families (Alfa/Beta/Delta) cross-validation with Schumann correlation.
  - Act 2: Omega spatial/cosmic corroboration.
  - Act 3: Loki Bayesian probability collapse (threshold 0.8).
  - Decision logic: THREE ACTS ALIGNED = MAX CONFIDENCE ALERT (0.98).
  - Veto logic: Loki probability below threshold blocks full confirmation.
- **Juez (Disciplinary Engine)**: Implemented Asymmetric Punishment Law.
  - **JUEZ LAW**: If Padre fails corroboration (Miss on real event), punishment is DOUBLE for Padre AND the originating bots that alerted.
  - Severity scaling: Exponential (gravity^2) for false negatives.
  - Recidivism tracking per bot.
  - Fase separation: viva (live ops) vs reconocimiento/backtest/observacion (training) to prevent contamination.

### Technical Details
- Padre now extracts Omega and Loki signals separately for hierarchical evaluation.
- Loki validation requires probability >= 0.8 for final confirmation.
- Juez applies extra severity (SEVERIDAD_FALLO_BASE) to both Padre and originating bots on corroboration failure.

## [Unreleased] - 2026-09-04 - Padre & Juez Implementation Complete

### Added
- **Padre Agent (GeodynamicPadre)**: Full Three-Act Consensus Hierarchy implemented.
  - Act 1: SNT Families (Alfa/Beta/Delta) cross-validation with Schumann correlation (>0.3).
  - Act 2: Omega spatial/cosmic corroboration required.
  - Act 3: Loki Bayesian probability collapse (threshold >= 0.8) for final confirmation.
  - Decision matrix: THREE ACTS ALIGNED = MAX CONFIDENCE ALERT (0.98).
  - Veto logic: Loki below threshold blocks full confirmation; SNT+Omega can alert without Loki.
  - Loki signals extracted and validated separately in hierarchical evaluation.
  - Omega elevation logic preserved for reference scenarios.
  
- **Juez Agent (Disciplinary Engine)**: Asymmetric Punishment Law implemented.
  - **JUEZ LAW**: If Padre fails corroboration on real event (MISSED_EVENT), punishment is DOUBLE for Padre AND originating bots that alerted (informant bonus for those who were right).
  - Severity scaling: Exponential (gravity^2) for false negatives.
  - Recidivism tracking per bot in TBL_PESOS_BOTS.
  - Phase separation: viva (live ops) vs reconocimiento/backtest/observacion (training) to prevent contamination.
  - Weight floor at 0.2 to maintain voting diversity.
  - Informant bonus (+0.1) for bots that correctly alerted while Padre ignored.

- **Loki Integration in Pipeline**: 
  - GeodynamicLayerRunner now instantiates and runs LokiAgent.
  - Loki ingests Bz, Solar Wind, Schumann, VIX, LOD data.
  - Loki signal passed to Padre for Three-Act evaluation.

### Technical Details
- Padre extracts Omega and Loki signals separately for hierarchical evaluation.
- Loki validation requires probability >= 0.8 for final confirmation.
- Juez applies double severity to both Padre and originating bots on corroboration failure.
- Audit trail stored in TBL_JUEZ_AUDITORIA with full cycle reconstruction.

## [Unreleased] - 2026-09-04 - Loki Pipeline Integration

### Added
- **GeodynamicLayerRunner**: Full Loki integration into the execution pipeline.
  - LokiAgent instantiated in __init__ as part of the core agent suite.
  - Loki data extraction from pipeline: Bz GSM, Solar Wind, Schumann Resonance, VIX, LOD.
  - Loki ingestion and analysis executed in run() cycle before Padre consensus.
  - Loki signal appended to the signals list passed to Padre for Three-Act evaluation.
  - Logging of Loki signal type and confidence for telemetry.

### Technical Details
- Runner now imports LokiAgent from sentinel_omega.layers.geodynamic.loki.agent.
- Loki receives real-time space weather, Schumann, financial, and rotational data.
- Loki's Bayesian probability collapse result feeds directly into Padre's hierarchical consensus.
- All agents now execute in the correct order: SNT Families -> Omega -> Loki -> Padre.

## [Unreleased] - 2026-09-04 - Dev Retraining Complete & Back-end Validated

### Added
- **ONNX Models Retrained (Bootstrap)**: All 6 agents retrained on synthetic data (2500 samples each)
  - alfa1_spaceweather_rf.onnx (785,805 bytes) — Space Weather (30 yr)
  - alfa2_satellite_cnn.onnx (32,222 bytes) — Satellite Thermal (14 yr)
  - beta1_schumann_fft.onnx (466,483 bytes) — Cymatic Artist (30 yr)
  - beta2_atmospheric_cnn.onnx (30,834 bytes) — Atmospheric Analyst (14 yr)
  - delta_financial_lstm.onnx (80,330 bytes) — Financial Sentiment (10 yr)
  - omega_espacial_rf.onnx (259,110 bytes) — Cosmic Correlator (30 yr)
- **Alfa-2 Historical Baseline**: Computed from 2,301 satellite records (tbl_cobertura_satelital)
  - 3 zones: guerrero_gap, oaxaca_costa, chiapas
  - Stored at 
  - Alfa-2 now loads baseline on startup — ZERO live training

### Validated
- All agents import and instantiate correctly
- All ONNX models load and infer (confidence + signal outputs verified)
- GeodynamicLayerRunner integrates Loki Agent in pipeline
- Padre consensus hierarchy: SNT Families → Omega → Loki (Three Acts)
- Juez asymmetric discipline engine operational (TBL_JUEZ_AUDITORIA: 901,852 records)
- Alfa-2 historical baseline loaded at runtime (no live training)

### Status
**BACK-END v2.5.4 COMPLETE** — Ready for dashboard/frontend simplification (19 → 6 tabs)
