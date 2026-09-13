## 2026-09-13 — Puente seguro DeamonX ↔ Ollama (Agente-C + G + A)

### Added
- `~/bridge/`: sshd bootstrap/harden, `check_bridge.sh` (con jq), `TERMUX.md`, `README.md`
- sshd Kali pubkey-only; Termux key `SHA256:Euih1Lj…`; firewall Windows `WSL SSH 22` Private+Public
- Túnel verificado: Termux `192.168.1.137` → Kali `:22` → Ollama `127.0.0.1:11434` (`/api/tags` OK)
- `REMOTE_MODEL=concilio-lightest:latest` (sin deepseek-r1:8b en host)
- `jq` 1.8.1 en Kali para checks

### Notes
- No se abrió Ollama a LAN (`0.0.0.0`)
- autossh en Termux: script A en `~/deamonx_mobile/bin/tunnel_ollama.sh` (opcional)

## 2026-09-13 — DeamonX-Mobile bridge + host ops (Termux ↔ X-Deamon)

### Added
- Puente **DeamonX-Mobile** (Honor X7d / Termux) ↔ **X-Deamon** (Kali WSL): SSH pubkey-only + túnel `-L 11434` hacia Ollama en loopback.
- Scripts/conf en `/home/deamon/bridge/`: `TERMUX.md`, `check_bridge.sh`, `install_sshd.sh`, `sshd_bootstrap.conf`, `sshd_deamonx.conf`.
- Doc de sesión: `docs/DEAMONX_BRIDGE_2026-09-13.md`.
- `jq` instalado (listado de modelos en chequeo del puente).

### Changed / Ops
- Wi-Fi **Private** + firewall permitiendo SSH/WSL puerto **22**.
- Autostart WSL Kali al login de Windows (tarea `WSL-Kali-Autostart`).
- Ollama runtime = Windows `ollama.exe`; `ollama.service` en Kali **disabled**.
- Termux env: `REMOTE_OLLAMA_URL=http://127.0.0.1:11434`, `REMOTE_MODEL=concilio-lightest:latest`.

### Security
- **Nunca** `OLLAMA_HOST=0.0.0.0` / bind LAN sin OK explícito del operador.
- `sshd`: PasswordAuthentication no, PubkeyAuthentication yes, AllowUsers deamon (ver confs en `bridge/`).

### Concilio / Sentinel (mismo día, contexto)
- Concilio: `/task` light + pack; `/concilio` heavy; Mini App vía `cloudflared`.
- Sentinel: scheduler disabled, 1 launcher; docs `SESSION_2026-09-13.md` / `SYSTEM_HEALTH_2026-09-13.md` ya existentes.

### Roles
- **G** coord/sudo · **C** host/sshd · **T** Concilio/TG · **A** DeamonX mobile.

---


## [home] - 2026-09-13 — Concilio/Telegram ops note

### Added / Documented
- Home `AGENTS.md`: seccion **Concilio / Telegram (ops 2026-09-13)** (`/task` ligero vs `/concilio`, Mini App HTTPS `cloudflared-mini`, Ollama Windows).
- Consensus **2.2.6**: tunel Mini App + `TELEGRAM_WEBAPP_URL` auto.

## 2026-09-13 — Ops Sentinel/Watchdog + docs (sección Agente-C)

### Fixed / Ops (Agente-C + pares)
- Validación post-fix duelo launchers: omega solo, scheduler disabled.
- Schumann tests (`test_pipeline.py::TestSchumannConnector`) 6/6; `pytrends` instalado en `/home/deamon/workspaces/.venv`.
- Docs sesión/health: `workspaces/sentinel_omega/docs/SESSION_2026-09-13.md`, `SYSTEM_HEALTH_2026-09-13.md`.

### Notes
- Ollama runtime documentado como Windows `ollama.exe`; unit Kali disabled.
- Backup offbox catch-up 13-1253; hueco 12-sep no reconstruible (WSL dormido).
- Alfa2 tests: ver cierre Agente-T (7 passed).

## 2026-09-10/11 — Dashboard 6 tabs, ingest Schumann/Delta, ONNX retrain

- Dashboard React: exactamente 6 tabs; APIs RO schumann_vivo/delta/clima_espacial; promovido Dev→Test→Prod.
- Telegram messaging: eliminado copy "lotería" de alertas/digest.
- Ingest: WPC Tomsk (linaje Drive extractor_vision_schumann); sin fallback falso 7.83/0; Schumann vivo 8.26/21.46; clima 2026 gapfill; sismos refetch; Delta no escribe all-zero.
- ONNX: wipe+retrain; Prod deja bootstrap-only y gana Loki.
- Docs: SESSION_2026-09-10.md, SYSTEM_HEALTH, INGEST_FIX, TRAIN_RESTART, DASHBOARD_6TABS_DONE.
- No corrido: launcher --entrenar firmas.


## 2026-09-10 Dashboard 6 tabs DEV
- 19 to 6 tabs; API schumann_vivo delta clima_espacial; port 5174; see DASHBOARD_6TABS_DONE.md

# Changelog — Home Workspace (/home/deamon/)

All notable changes to projects in /home/deamon/ are documented here.  
Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.  
Dates are UTC-6 (local time of the author, México).

---

## [Unreleased] - 2026-09-10 - Lottery scrub + dashboard 6 tabs a Prod + health/ingest docs

### Changed
- Messaging: copy loteria scrubbed en Dev/Test/Prod (alert_service.py, consenso_vigilante.py); servicio reiniciado ~18:06 CST.
- Sentinel Omega dashboard React: 6 tabs (Principal/Familias/Omega/Loki/Padre+Juez/Modelos) + API RO schumann_vivo/delta/clima_espacial promovido Dev→Prod flat+nested (~18:12–18:15 CST).
- Docs: SYSTEM_HEALTH_2026-09-10.md (health OK, lottery, DB empty/flat), DASHBOARD_6TABS_DONE.md, INGEST_FIX_2026-09-10.md stub (pending fix agent).

### Notes
- Health servicios/puertos/HTTP OK. DB ~873M no tocada; correlaciones vacias / series flat bajo auditoria.
- Streamlit 8501 legacy intacto. Entrenar/firmas/remapeo NO habilitado.
- Vite 5174 tipicamente desde Dev; launcher Prod puede no servir React sin npm run dev / build.

---


## [Unreleased] - 2026-09-03 - Concilio (consensus-expert-agent) documentado en home

### Added
- Home README / AGENTS: tercer proyecto **Concilio** en `/home/deamon/consensus-expert-agent/` (pipeline secuencial Ollama, umbral 85%, Telegram bridge, relacion con Sentinel Omega).
- Referencias a `consensus-expert-agent/AGENTS.md` y `CONCILIO.md`.

### Changed
- Modelos de consenso documentados como `concilio-worker`/`concilio-arbitro` + bases `qwen2.5:1.5b`/`gemma4:26b` (ya no Nemotron/DeepSeek como identidad).
- Politica actual: `inject_sentinel_architecture: false` por defecto; `.concilio` = DATA; fast Gente/Estado fuera del Concilio.
- Arbol de directorios home actualizado (workspaces-dev/test + consensus-expert-agent).

### Notes
- Detalle de version del agente: consensus CHANGELOG **2.2.1** (sobre Concilio 2.2.0 + audit 2.1.1).

---

## [Unreleased] - 2026-09-02 - Home workspace context files

### Added
- README.md — Contexto unificado de ambos proyectos (Sentinel Omega + Padrón de Afiliados).
- CHANGELOG.md — Este archivo.
- AGENTS.md — Reglas operativas para agentes IA en este workspace.

### Changed
- Sentinel Omega (en /home/deamon/workspaces/sentinel_omega/):
  - Tests: 430/430 pasando (fix import orchestrator en test_infrastructure.py).
  - Watchdog de seguridad documentado y verificado.
  - Consenso Padre operativo con pérdida asimétrica 10:1.
  - Telegram enriquecido: gráficas, tablas, cimática (v2.5.3).
  - Dashboard 11 tabs operativo.

- Padrón de Afiliados (en /home/deamon/padron_afiliados_app/):
  - Estructura completa: src/, database/, tests/, logs/, venv/.
  - DB schema (6 tablas + vista) inicializada.
  - analisis_comportamiento.py — 9 funciones de análisis + reportes.
  - app_afiliados.py — Streamlit 11 tabs (esqueleto funcional).
  - Tests: 2/2 pasando (integración + resumen ejecutivo).
  - Pendiente: Primer commit Git + rama local/padron-v1.0.0.

---

## [2.5.3] - 2026-09-01 - Sentinel Omega: Fixes operativos + corrección 125 nodos UVG

### Fixed
- launcher.py: _check_already_running captura PermissionError (pid root visto desde deamon).
- shutdown.py: _process_alive resiliente a PermissionError; sugiere sudo kill.
- deploy/generar_reporte.py: Detecciones deduplicadas por GROUP BY tipo; texto Molchan corregido a 125 nodos UVG (75 reales + 50 Ghost).

### Verified
- launcher.py --once con pid root → exit 1 controlado.
- shutdown.py con pid root → mensaje sudo claro.
- pytest test_precursor / test_schumann_filter → PASS.

---

## [2.5.3] - 2026-08-29 - Sentinel Omega: Alertas enriquecidas Telegram

### Added
- infrastructure/api/telegram.py: send_photo(), send_document().
- infrastructure/messaging/charts.py: fantasma_timeline(), cimatica_bars(), precursores_tabla_png().
- infrastructure/messaging/alert_service.py: Templates cimatica_consistente(), reporte_resumen().
- core/firmas/cimatica.py: Auto-alerta en frecuencia 3 + envío foto cimatica_bars.
- orchestrator.py: Enriquecimiento alertas precursor + tabla activos + cimática top-3 + fantasma_timeline.

### Changed
- Umbral precursor 0.7 → 0.5 (más cobertura).
- Dashboard: 9 → 11 tabs (nueva pestaña Cimática + Fantasma enriquecido).

### Verified
- registrar_snapshot x3 → frecuencia 3 dispara Telegram OK.
- fantasma_timeline([3,5,8,12]) → 36K PNG OK.
- Suite completa 389 tests PASS.

---

## [1.0.0] - 2026-09-02 - Padrón de Afiliados: Estructura inicial

### Added
- Estructura modular: src/, database/, logs/, tests/, venv/.
- database/schema.sql — 6 tablas + índices + vista v_estadisticas_generales.
- src/analisis_comportamiento.py — 9 análisis (demográfico, participación, cohortes, cimática, redes, outliers) + reportes JSON.
- src/app_afiliados.py — Streamlit 11 tabs (Dashboard, Afiliados, Importar, Análisis, Eventos, Participación, Alertas, Telegram, Cimática, Redes, Config).
- tests/test_analisis.py — Tests de integración y resumen ejecutivo (2/2 PASS).
- requirements.txt — 12 deps pinned (pandas 3.0.5, streamlit 1.63.0, scipy 1.18.1, etc.).
- .gitignore — Excluye *.db, venv/, __pycache__/, *.log, .streamlit/.

### Git
- Repo inicializado en /home/deamon/padron_afiliados_app/.git.
- Pendiente: Primer commit + rama local/padron-v1.0.0.

---

## [2.5.0] - 2026-08-19 - Sentinel Omega: Cableado pipeline completo

### Added
- Schema v11: tbl_locf_cache, tbl_eventos_catalogo, DDL self-expanding.
- LOCF: Último valor real en DB si falla API (cero sintéticos).
- ONNX: Modelos + mixin para alfa1/2, beta1/2, delta, omega; train desde DB + Juez.
- Juez 2h: Ritmo cada 2h; castigo/refuerzo a todos los bots.
- Launcher self-expanding desde launcher_hex/; ventana_h adaptativa.
- Omega dual-ask + puerta de referencia por asertividad.
- Telegram Centinela V2 con gate 30 min y credenciales solo por env.
- Volcado 24h: Telemetría viva → histórico en cascada.
- Dashboard: Pestañas Alfas / Betas / Omega / Padre / Juez / Eventos / Agente (consenso).
- Mensajería: AlertService unificado + ReportEngine versionado.
- Agente: consensus-expert-agent (Concilio) umbral 85/100; hoy thin (`inject_sentinel_architecture: false`); modo --audit.

---

## Notas de Versión

| Proyecto | Versión Actual | Rama Git Activa | Estado |
|----------|----------------|-----------------|--------|
| Sentinel Omega | 2.5.3 | local/alertas-v2.5.3 | Producción |
| Padrón de Afiliados | 1.0.0 | (sin rama) | Esqueleto |
| Concilio (consensus-expert-agent) | 2.2.1 | (repo propio) | Standalone thin (inject Sentinel off) |

Convención de ramas: local/<feature>-v<version> — nunca push directo a main.
