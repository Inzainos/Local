## [2.2.6] - 2026-09-13 — Mini App HTTPS (cloudflared-mini)

### Added
- User-unit `cloudflared-mini.service` + `scripts/run_cloudflared_mini.sh`: quick tunnel a `:8002`, publica URL trycloudflare, actualiza `TELEGRAM_WEBAPP_URL=.../mini` y reinicia el bot.
- `Linger=yes` para usuario `deamon` (tunel sobrevive sin sesion interactiva).

### Changed
- `CONSENSUS_DASHBOARD_URL` default/.env -> `http://127.0.0.1:8002`.

### Notes
- URL trycloudflare es **efimera** (cambia al reiniciar el tunel). Tunel nombrado/ngrok = escalacion futura.
- Builds on **2.2.5** (light/heavy cut).

## [2.2.5] - 2026-09-13 — Telegram light/heavy cut + audit Sentinel

### Changed
- `/task` ahora es vía **ligera**: `orchestrator.fast_ask(..., preload_sentinel=True)` (pack `data/memory_packs/sentinel_omega_pack.md`, tope ~8k).
- `/concilio` queda para el **Concilio completo** (light→medium→heavy→verify, umbral 85).
- Preguntas de eventos/precursores/muro/alertas en `/task` leen la **DB Sentinel** (`sentinel_proximos_eventos`), no alucinan TV.
- `/help` y menú alineados: `/task` ligero · `/concilio` heavy.
- `audit_project(..., with_sentinel=True)` inyecta pack/pipeline Sentinel **solo** durante `/audit`; restaura `inject_sentinel_architecture` al valor previo (default config sigue `false` para runs normales).

### Fixed
- Auth de `/concilio` usa `is_authorized` (no `_ensure_auth` inexistente).

### Ops
- Units `consensus-telegram.service` y `consensus-web.service` (:8002) documentados como deploy activo (`enabled`/`active` en host).
- Ollama API en `:11434` via **Windows** `ollama.exe` (unit Kali `ollama.service` se deja disabled para evitar choque de puerto).

### Notes
- Dashboard web `:8002` sigue en Concilio completo / fast paths de UI.
- Mini App local: `http://127.0.0.1:8002/mini` (botón Telegram necesita `TELEGRAM_WEBAPP_URL` HTTPS).
- No se tocó `.env` ni DB prod ni systemd de Sentinel en este doc bump.

## [2.2.4] - 2026-09-11 — Concilio reliability (full re-entry / score / session)

### Fixed
- **Full re-entry** when verified score < 85: loop is lightest → medium → heavy → lightest verify (not coder-only refine). Respects `max_refinement_rounds` and `auto_refine`.
- **Unload always runs**: `_run_exclusive` unloads in `finally` even if stage callbacks throw.
- **Score parse robustness**: verifier accepts `[PUNTUACION_VERIFICADA|CONSENSO]` and `score: N`; no longer grabs arbitrary first digits.
- **Session write durability**: `.concilio` save uses tmp + `fsync` + `os.replace` (+ dir fsync best-effort).
- **Quarantine** leftover `engine/orchestrator.py.broken`.

### Changed
- `health().concilio.order` documents full re-entry path.

### Notes
- Does not touch `.env`, Sentinel prod DB, or systemd units.
- Telegram bot / Mini App paths untouched.

# Changelog

## [2.2.3] - 2026-09-10 — Prod deploy units

### Added
- `deploy/consensus-telegram.service` y `deploy/consensus-web.service` (Mini App en **:8002**; :8000 ocupado).
- Bot Telegram ya en ejecución bajo usuario `deamon`; web Mini App en `http://127.0.0.1:8002/mini`.

### Notes
- Instalar units requiere sudo (ver docs/FUNCIONAMIENTO_TELEGRAM.md).
- Sentinel `sentinel-omega.service` ya estaba **active** en este host.


## [2.2.2] - 2026-09-10 — Telegram status/reporte + Mini App

### Added
- `/status` enriquecido y nuevo `/reporte`: Concilio health (umbral 85, sequential, model tags, sesiones `.concilio`, `alert_queue.get_stats`) + Sentinel read-only; sin secretos.
- Mini App `static/mini.html` servida en `/mini` y `/static/`; API `/api/mini/status` (+ `/mini` / `/static/mini.html`).
- `TELEGRAM_WEBAPP_URL` en `.env.example`; botón WebApp en `/start` cuando la URL está configurada.
- Link README → `docs/HANDOFF_GEMMA_MEMORIA.md`.

### Changed
- `TELEGRAM_BOT_README.md` documenta Mini App, `/status` y `/reporte`.
- Politica alertas: digest horario siempre; inmediato solo sin precedentes; bot = `/task` + reportes + cola.

### Notes
- Leftover: HTTPS publico para `TELEGRAM_WEBAPP_URL` (Telegram Mini App).
- No se reescribio el orchestrator; no se toco Sentinel prod; no se volco `.env`.

---

## [2.2.1] - 2026-09-03 — Docs/config thin + home hard-rules sync

### Added
- `AGENTS.md` local (apunta a `/home/deamon/AGENTS.md` + reglas Concilio).
- Stub opcional `data/memory_packs/home_hard_rules_stub.md` (mapa home + reglas duras; **no** auto-inject).
- Comentarios de hard rules / project map al inicio de `config.yaml`.
- `concilio.inject_sentinel_architecture: false` y `context_injector.enabled: false` explícitos.
- `concilio.hard_rules_stub` path documentado.

### Changed
- Roles renombrados a Worker-Research / Worker-Coder / Arbitro (ya no Nemotron/DeepSeek como identidad).
- Modelos preferidos: `concilio-worker` / `concilio-arbitro` (fallbacks `qwen2.5:1.5b` / `gemma4:26b`).
- System prompts thin con reglas home inline (secretos/env, cero sintéticos, forward-only, no prod DB) sin exigir corpus Sentinel.
- `ResearcherAgent` ya **no** auto-carga `load_repository_context()` cuando inject=false.
- Preferencia de tags Ollama: con inject=false prioriza `concilio-*` antes que `sentinel-concilio-*`.
- README / CONCILIO.md / docs/CONCILIO.md alineados a la realidad actual.

### Policy
- Sin inyección Sentinel por defecto hasta que terminen updates Sentinel en otro hilo.
- Builds on Concilio **2.2.0** + audit **2.1.1**.

---

## [2.2.0] - 2026-09-03 — Concilio thin (no Sentinel injection)

### Added / Fixed
- Full Concilio order: LIGHTEST -> MEDIUM -> HEAVY -> LIGHTEST verify.
- Between stages: write data/sessions/<id>.concilio + unload (never two models).
- If score < 85: full re-entry (not coder-only refine) until threshold or max_refinement_rounds.
- .concilio / UNTRUSTED_DATA fenced as DATA (memory/anti_injection.py + ConcilioStore).
- Thin Modelfiles (modelfiles/Modelfile.lightest|medium|heavy); scripts/create_concilio_models.sh.
- config: concilio.inject_sentinel_architecture: false; context_injector.enabled: false.
- researcher no longer auto-loads Sentinel repository_context.
- main.py --check reports tiers and unloads models.

### Policy
- Do NOT use Modelfile.sentinel-concilio-* for default Concilio.
- Builds on audit v2.1.1.


## [Unreleased] — 2026-09-03 — Sequential Concilio + Sentinel Modelfiles

### Added
- **Sequential Concilio**: one agent at a time; write `data/sessions/<id>.concilio`; `ollama stop`/unload before next role so `gemma4:26b` / `sentinel-concilio-arbitro` can run as final arbiter without sharing RAM.
- **`.concilio` store** (`memory/concilio_store.py`): JSON sections task/research/code/critique/scores/round; Concilio-roles-only; not web-UI executable.
- **Anti-injection** (`memory/anti_injection.py`): fence/strip untrusted blackboard & user content; preamble DATA_NOT_INSTRUCTIONS.
- **Memory pack** `data/memory_packs/sentinel_omega_pack.md` (+ `scripts/build_memory_pack.py` from DEV docs; no `.env` secrets).
- **Modelfiles**: `sentinel-concilio-arbitro` (FROM gemma4:26b), `sentinel-concilio-worker` (FROM qwen2.5:1.5b) + `scripts/create_concilio_models.sh`.
- **CONCILIO.md** short ops guide. Documents dashboard `POST /api/ask` (Estado; no "Gente" tab) as OUTSIDE Concilio.

### Changed
- `config.yaml`: researcher/coder → `sentinel-concilio-worker` (fallback `qwen2.5:1.5b`); optimizer → `sentinel-concilio-arbitro` (fallback qwen). Threshold single **85**.
- `engine/orchestrator.py`: exclusive model lifecycle per role; sync `.concilio` after each stage.
- `memory/blackboard.py` + `agents/researcher.py`: fenced prompts.

### Policy
- Never keep 26b + another chat model loaded together.
- Do not touch Sentinel prod DB / systemd from this agent.


# Changelog - Consensus Expert Agent / Concilio

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-09-03

### Added — Standalone Concilio pipeline (chain/rhythms)
- **Sequential unload**: un modelo Ollama en VRAM a la vez (`keep_alive: 0` + `unload()` entre roles).
- **Session files**: `data/sessions/<id>.concilio` tras cada etapa (INIT/RESEARCH/CODING/REVIEW/REFINE/SYNTHESIS).
- **DATA fencing**: `<<<CONCILIO_DATA_NOT_INSTRUCTIONS>>>` … `<<<END_CONCILIO_DATA>>>` al reinyectar sesión/pizarra.
- **Thin Modelfiles** opcionales: `modelfiles/Modelfile.worker` (FROM qwen2.5:1.5b), `modelfiles/Modelfile.arbitro` (FROM gemma4:26b) — SYSTEM solo anti-inyección + formato de score.
- **CONCILIO.md**: descripción breve de la cadena/rhythms (sin arquitectura Sentinel).
- **`pipeline` + `context_injector.enabled: false`**: modo standalone por defecto.

### Changed
- System prompts de roles: sin corpus Sentinel; umbral único **85** (sin gap 80–84).
- Nombres de rol: Worker-Research / Worker-Coder / Arbitro-Gemma; `preferred_model` concilio-* si existe.
- Researcher/Coder/Optimizer dejan de exigir reglas Sentinel en prompts de usuario.
- README alineado al pipeline standalone.

### Notes
- Integración Sentinel diferida (otro agente). No se tocó DB de producción ni se volcaron secretos `.env`.

## [2.1.1] - 2026-09-03

### Fixed — Audit Kali WSL
- **Optimizer prompt gap**: system prompt decía aprobar ≥85 pero exigir cambios solo si <80 (80–84 indefinido). Ahora un solo umbral alineado a `consensus.threshold_score` (85).
- **`alert_queue.get_stats()`**: `/queue` del bot llamaba un método inexistente → AttributeError. Implementado con contadores persistentes, `requeue`, `mark_sent`/`mark_failed` y escritura atómica.
- **Alert poller**: si el envío a Telegram falla, la alerta se reencola (antes se perdía tras `pop_batch`).
- **`timeout_retries`**: estaba en `config.yaml` pero no se usaba; ahora reintenta timeouts/transporte en `BaseExpertAgent.generate`.
- **SQLite path**: `data/shared_memory.db` relativo se resuelve contra el directorio del `config.yaml` (no contra el CWD).
- **Context injector**: orden de `workspace_roots` pasa a preferir `workspaces-dev` → `workspaces-test` → `workspaces` (prod al final).
- **Telegram auth**: callbacks inline ahora pasan por `is_authorized`; chat IDs separados por coma se comparan con `.strip()`.
- **`run_telegram_bot.sh`**: carga `.env` correctamente.
- **Score parse**: fallbacks del optimizador usan el threshold configurado.
- **Pipeline routing**: RESEARCH/QA omiten fase de código y refinamiento inútil.
- **README**: alineado a modelos instalados (`qwen2.5:1.5b`, `gemma4:26b`).
- **deps**: `python-dotenv` añadido a `requirements.txt`.

### Notes
- Roles Nemotron/DeepSeek/Gemma como nombres; researcher/coder compartían binario hasta especialización.
- No se tocó la DB de producción de Sentinel Omega.

## [2.1.0] - 2026-09-01

### Added - Telegram Bot Integration
- Bidirectional Telegram integration (Consensus ↔ Sentinel alerts)
- Bot commands: `/task`, `/audit`, `/status`, `/blackboard`, `/cancel`
- See TELEGRAM_BOT_README.md

## [2.0.0] - 2026-08-XX

### Added - Core Consensus System
- Multi-model consensus engine via Ollama
- Shared memory blackboard (SQLite)
- Iterative refinement with consensus scoring (0-100)
- Web dashboard + CLI

## [1.0.0] - 2026-08-XX

### Added - Initial Release
- Basic consensus orchestrator, memory, configuration
