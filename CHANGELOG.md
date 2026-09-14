# Changelog — Sentinel Omega


## [Unreleased] - 2026-09-13 - Cierre de pendientes GO Capitán (H1, H6, licencia)

### Removed
- `workspaces/.github/workflows/` completo (bandit.yml, codeql.yml,
  copy-delta-to-snt.yml, roy-vigilante.yml). Nunca corrían en esta rama
  huérfana — GitHub solo lee `.github/` en la raíz del repo, y `schedule:`
  solo dispara desde la rama por defecto. Operación 100% local vía systemd
  (`deploy/*.service` / `.timer`). H1 cerrado.

### Decided
- **Retención `estado/` (H6):** sin límite/purga, igual que `Inzainos/workspaces`
  (main), que tampoco poda — 799 archivos acumulados desde 2026-07-02 sin corte.
- **Licencia:** sin cambio. `Inzainos/workspaces` (main) declara la misma
  combinación — `LICENSE` raíz MIT + `sentinel_omega/pyproject.toml` con
  `Proprietary — Fractal Core Research` — así que no hay inconsistencia real
  entre monorepo y subproyecto; ya coincide con el repo de referencia.
- Detalle completo: `workspaces/sentinel_omega/docs/AUDIT_GITHUB_20260913.md`.

## [Unreleased] - 2026-09-13 - Metadata de rama: README de raíz

### Added
- `README.md` de raíz: qué es el sistema, tabla de bots, estructura, comandos y
  enlaces a `workspaces/README.md` y `AGENTS.md`. Antes era un stub de ocho líneas.
- Sección **Notas de estructura** con cuatro hallazgos verificados contra el árbol,
  documentados sin modificar nada:
  1. **Directorio `models/` canónico = `workspaces/sentinel_omega/models/`.** Su
     `models_meta.json` es del 2026-09-13T09:05Z con muestras mayores (alfa1 1388,
     beta1 2082, omega 2726); el anidado `sentinel_omega/sentinel_omega/models/` es
     del 2026-09-11T00:20Z (1303, 1997, 2556). El campo `path` de ambos meta apunta
     al mismo destino absoluto `/home/deamon/workspaces/sentinel_omega/models/`, y
     coincide con el `base_dir` por defecto de `config/onnx_config.py`
     (`sentinel_omega/models`, relativo al CWD). El anidado es copia congelada.
  2. Los 4 workflows están en `workspaces/.github/workflows/`, no en la raíz del
     repositorio: GitHub no los ejecuta. Los `schedule:` además solo disparan desde
     la rama por defecto.
  3. `workspaces/.agents/skills/developing-with-streamlit` apunta dentro de `.venv/`
     (gitignorado): queda roto en checkout limpio.
  4. `LICENSE` de raíz dice MIT y `pyproject.toml` dice
     `Proprietary — Fractal Core Research`. Pendiente de resolver.

### Notes
- Sin cambios en código, modelos ni datos.


## [Unreleased] - 2026-09-03 - Consenso Telegram: digest horario + solo sin precedentes

### Added
- `infrastructure/messaging/consenso_vigilante.py` — el Padre (bot de consenso) agrupa avisos de los demás bots.
  - **Reporte horario SIEMPRE** (`TG_DIGEST_MINUTES=60`): Fantasma+nivel, muro n/5, telemetría one-liners, top precursores, loop vivo/muerto, botón Mini App. No se salta la hora aunque esté calma. No es un montón de pings "precursores revisar".
  - **Telegram inmediato SOLO si `is_unprecedented`**: sin registro previo en el sistema. Califica: cimática NUEVO (`tbl_cimatica_patrones.frecuencia==1`), firma nunca vista (`TBL_FIRMAS` estado=`nueva` / recurrencia≤1), tipo de muro breach nuevo, `SYSTEM_DEAD` (loop muerto). Firmas recurrentes y precursores de siempre → solo el reporte horario. El cooldown `send_alert_gated` (1800s) se conserva en el path inmediato para no spamear el mismo tipo.
  - Mini App: `infrastructure/dashboard/static/mini.html` servida por FastAPI en `/mini`. Botón `web_app` si `TELEGRAM_WEBAPP_URL` es HTTPS público. No se fabrica túnel.
- Templates nuevos/enriquecidos (español, captions de qué significa el número, sin claims de lotería): `cimatica_nuevo`, `firma_nueva`, `muro_breach`, `sin_precedente`.
- Tests: `tests/test_consenso_vigilante.py` (buffer vs immediate, digest vacío, cooldown, DB firmas/cimática, dry_run, cero red).

### Changed
- `AlertService.dispatch` canal Telegram pasa por el vigilante; correo y log siguen igual.
- `orchestrator.py` ya no dispara `send_alert_gated`/`send_photo` por cada precursor ≥0.5; ingesta al vigilante y `maybe_flush` al cierre de ciclo.
- `dispatch_cycle_alerts` y cimática consistente dejan de pagear; cimática NUEVO sí (sin precedentes).
- Env: `TG_DIGEST_MINUTES` (default 60), `TELEGRAM_WEBAPP_URL` (HTTPS), `SENTINEL_DRY_RUN`.

### Policy (Elán)
Digest horario siempre. Immediate = solo lo que no tiene registro. No hay page por rojo/naranja rutinario.

---
All notable changes to the Sentinel Omega precursor detection system are
documented here. Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
conventions. Dates are UTC-6 (local time of the author).

---
## [Unreleased] - 2026-09-01 - Fixes operativos + corrección 125 nodos UVG

### Fixed
- `sentinel_omega/launcher_hex/h00..h11.hex`: `_check_already_running` ahora captura `PermissionError` (pid de root visto desde deamon) → `return True` en vez de traceback; `_clear_pid` resiliente a `OSError`. Backup en `launcher_hex_backup_1788196565/`. Verificado: `launcher.py --once` con pid root ahora responde `ERROR already running` limpio.
- `sentinel_omega/shutdown.py`: `_process_alive` captura `PermissionError` → `True`; `shutdown()` detecta pid de otro usuario y sugiere `sudo kill -TERM <pid> && sudo rm data/sentinel_omega.pid` en vez de colgarse 30s.
- `deploy/generar_reporte.py`: detecciones deduplicadas por `GROUP BY tipo` con `MAX(id)` + rehidratación → 6 tipos distintos en lugar de 8 filas duplicadas (SEISMIC_CLUSTER/SILENT_TRIGGER x4); texto Molchan corregido `50 nodos reales` → `125 nodos UVG (75 reales + 50 Ghost)` con dispersión global nodal. Reporte regenerado `2026-09-01_09-00_MX.md`.

### Verified
- `python sentinel_omega/launcher.py --once` con pid root → exit 1 controlado
- `python sentinel_omega/shutdown.py` con pid root → mensaje sudo claro
- `python deploy/generar_reporte.py` → REPORTE.md con 6 precursores distintos y texto 125 nodos
- `pytest test_precursor / test_schumann_filter` → PASS

## [Unreleased] - 2026-08-29 - Alertas enriquecidas Telegram (v2.5.3 - graficas, tablas, cimatica)

### Added
- `infrastructure/api/telegram.py`: `send_photo(path, caption)` y `send_document(path)` - envio de PNG/PDF a Telegram (caption HTML 1000 chars, timeout 20s, usa TELEGRAM_BOT_TOKEN/CHAT_ID).
- `infrastructure/messaging/charts.py` (95 lineas, nuevo): generador de graficas con `matplotlib Agg` (sin display) en `/tmp/sentinel_charts/` (env `SENTINEL_CHARTS_DIR`):
  - `fantasma_timeline(valores, labels, titulo)` - linea Fantasma con bandas AMARILLO 15 / ROJO 30, punto final rojo si activo, 36K PNG verificado.
  - `cimatica_bars(patrones, titulo)` - barras frecuencia por patron_id (verde si tiene event_class).
  - `precursores_tabla_png(filas, titulo)` - tabla precursores como imagen.
- `infrastructure/messaging/alert_service.py`: nuevos templates `AlertTemplates.cimatica_consistente()` (patron 3x, tabla + que significa) y `AlertTemplates.reporte_resumen()` (tabla 5 precursores + Fantasma/Muro/Consenso).
- `core/firmas/cimatica.py`: al alcanzar `frecuencia==3` dispara `AlertService.dispatch(telegram+log)` + envia `cimatica_bars` (top-5 `frecuencia>=2`) como foto via `send_photo` (no bloqueante, fail silencioso).
- `orchestrator.py`: enriquecimiento de alertas precursor - descripcion por tipo (schumann/sismo_cluster/solar/volcanic/cosmic/silent_trigger), tabla de todos los activos, cimatica top-3 (`tbl_cimatica_patrones WHERE frecuencia>=2`). Si `fantasma>5` genera `fantasma_timeline` (ultimos 10 de `tbl_salud_sistema`) y envia como foto con caption `Fantasma X | display_name`.

### Changed
- `orchestrator.py`: umbral precursor `0.7 -> 0.5` (mas cobertura, antes se perdian debiles).
- `sentinel_omega/README.md`: seccion `## Observabilidad y Resilience (v2.5.3)` con subseccion `### Alertas enriquecidas Telegram (v2.5.3)` documentando fotos, charts, templates y wire cimatica.

### Dashboard (v2.5.3)
- `infrastructure/database/repository.py`: `cimatica_top_patrones(limit=20)`, `cimatica_stats()`, `fantasma_timeline(limit=50)` - queries `tbl_cimatica_patrones` / `tbl_salud_sistema`.
- `infrastructure/dashboard/app.py` (11 tabs, +96 lineas): nueva pestaña 10 `Cimatica` con `render_cimatica()` (metricas, barras plotly, tabla 20, pie por clase, PNG Telegram) + pestaña 1 enriquecida con `Timeline Fantasma 50 ciclos` (bandas 15/30, scatter + hline) + vista previa Telegram.
- `sentinel_omega/README.md`: seccion Dashboard 9->11 tabs con tabla actualizada y bloque "Novedades v2.5.3".

### Verified
- `registrar_snapshot` x3 -> frecuencia 3 dispara Telegram OK (log "CIMATICA CONSISTENTE").
- `fantasma_timeline([3,5,8,12])` -> 36K PNG en `/tmp/sentinel_charts/fantasma.png` OK.
- `AlertTemplates.cimatica_consistente(1, "bz:-2|wind:4", 3, "SISMO_M5")` -> `CIMATICA` OK.
- `pytest sentinel_omega/tests/test_cimatica_correo.py` 23 passed; suite completa 389 passed (--ignore=test_pipeline.py).

## [Unreleased] - 2026-08-29 - Mejoras Estructurales (Observabilidad + Resilience + Config)

### Added
- **Config declarativa YAML** (config/sentinel.yaml, 60 lineas): defaults versionados (app, database, logging, api, telegram, pipeline, models, precursor, consensus, scheduler). config/sentinel_config.py con load_config(yaml_path) que mergea YAML + env vars (env gana), HAS_YAML fallback, seccion circuit_breaker en api.
- **Logging estructurado JSON** (infrastructure/logging/formatter.py, 50 lineas + __init__.py): JSONFormatter (timestamp UTC ISO, level, logger, module/func/line, extras, exception), setup_logging(level, log_file, fmt, max_bytes, backup_count) con RotatingFileHandler (10MB x 5) + console. Silencia urllib3/requests/httpx. Configurable json/text via sentinel.yaml (logging.format).
- **Health checks** (infrastructure/health/checks.py, 95 lineas + __init__.py): HealthChecker con 4 checks - database (SELECT name FROM sqlite_master, 5 tablas), disk (shutil.disk_usage, free_gb), apis (NOAA SWPC 200, latency_ms), pipeline (MAX(ts) en tbl_salud_sistema, age_hours; ok<2h/warn<6h/fail>6h). get_health() dict, CLI python -m sentinel_omega.infrastructure.health.checks. Estado: DB ok, disk 7% (949GB free), APIs ok (200ms), pipeline FAIL (294h sin ciclo).
- **Circuit breaker** (infrastructure/api/circuit_breaker.py, 95 lineas): CircuitConfig (failure_threshold=5, recovery_timeout=60, half_open_max_calls=3, success_threshold=2), CircuitBreaker thread-safe (CLOSED->OPEN->HALF_OPEN->CLOSED), registry global, decorador @circuit(name). Wireado a noaa.py (5 fetches), usgs.py, nasa_neo.py.
- **Resilience HTTP** (infrastructure/api/_http.py +10 lineas): tenacity (retry_api: 3 intentos, wait_exponential 1->10s, retry_if_exception_type(ConnectionError,Timeout), before_sleep_log) + fetch_with_retry(fn) ademas del urllib3 Retry (429/500/502/503/504, backoff 1s->4s).
- **Tooling centralizado** (pyproject.toml +24 lineas): dependencies +pyyaml, +tenacity, +python-dotenv; [tool.pytest] (testpaths, strict-markers, slow), [tool.ruff] (line-length 100, py310), [tool.mypy] (py310, ignore_missing_imports).
- **requirements.txt** +3 deps: tenacity>=8.2, pyyaml>=6.0, python-dotenv>=1.0; .gitignore +.env+logs/.

### Changed
- infrastructure/api/_http.py: import logging + tenacity, logger centralizado, wrapper fetch_with_retry.
- config/sentinel_config.py: +41 lineas (Path, yaml, load_config()), config = load_config() lazy YAML.
- sentinel_omega/.env.example: +NASA_API_KEY, LOG_LEVEL/FORMAT, CB_*.

### Fixed
- infrastructure/health/checks.py: WHERE type=table -> type=single-quoted table (syntax error), MAX(timestamp) -> MAX(ts) (columna real tbl_salud_sistema.ts), f-string join fix.
- infrastructure/api/_http.py: orden de imports (logging antes de requests, logger antes de retry_api).

### Verified
- pytest sentinel_omega/tests/ --ignore=test_pipeline.py: 389 tests OK. health, logging, circuit_breaker, _http, sentinel_config.load_config() imports OK desde workspaces.



## [Unreleased] — 2026-08-22

### Added
- **AlertService unificado** (sentinel_omega/infrastructure/messaging/alert_service.py, 137 lineas): centraliza reportes/alertas/mensajes Telegram/Correo/Log. Severity tipado ROJO/AMARILLO/VERDE/AZUL, FormattedMessage, AlertTemplates 7 templates puros (centinela_critico/grieta/tormenta/advertencia, precursor, consenso, sistema_online/dead, heartbeat) y AlertService.dispatch multi-canal con dry_run, gate anti-spam y outbox tbl_correo_salida fail-soft. Reemplaza 6 origenes dispersos; telegram.py/correo.py quedan como adapters intactos.
- **ReportEngine unificado** (sentinel_omega/infrastructure/pipeline/reporte_engine.py, 120 lineas): ReportEngine con render(tipo,filtros) y render_to_file versionando en estado/historial/AAAA/MM/ + actualizando estado/REPORTE.md. Delega a reporte_sentinel.py existente (871 lineas intactas), mantiene wrappers para scheduler_reportes.py sin cambios.
- **Dashboard pestana Agente** (sentinel_omega/infrastructure/messaging/agent_bridge.py 87 lineas + sentinel_omega/infrastructure/dashboard/agent_tab.py 100 lineas): agent_health lee config.yaml + data/shared_memory.db + ollama sin bloquear; agent_run_audit/agent_run_task via subprocess. render_agent_tab muestra metricas Root/DB/Ollama/Umbral 85, modelos, ultimos consensos e historial. Patch dashboard/app.py: 10a pestana Agente.
- **consensus-expert-agent fix contexto y consenso** (/home/deamon/consensus-expert-agent): repository_context prioriza estado/HANDOFF.md+INFORME_CORRECCIONES.md, shared_context.research_context, orchestrator loop while true hasta umbral 85, threshold 85 max_refinement_rounds 0, flags --audit/--focus/--check/--web. Validado qwen2.5:1.5b 95-100/100.

### Changed
- infrastructure/messaging nuevo paquete; infrastructure/pipeline/reporte_engine.py nueva capa DRY; infrastructure/dashboard/app.py 9 a 10 pestanas.
- **Autostart + Watchdog** (deploy/sentinel-omega-watchdog.service + sentinel_omega/infrastructure/watchdog/network_watchdog.py, 124 lineas): servicio systemd Restart=always con StartLimitInterval 300s, chequea red cada 60s (socket 8.8.8.8/1.1.1.1 + http fallback) y health del agente via agent_bridge; si falla 3 veces seguidas y hay red pero agente mal => systemctl restart sentinel-omega/scheduler; si vuelve red => notifica via AlertService y re-levanta servicios caidos. sentinel-omega.service ahora RestartSec 10 + StartLimit. install.sh instala y habilita watchdog.

### Fixed
- Dispersion de formatos de alerta (6 origenes) y duplicacion de severidad/cooldown; single source of truth testeable.

## [Unreleased] — 2026-08-19

> **Detalle completo:** [`CHANGELOG_2026-08-19.md`](CHANGELOG_2026-08-19.md)

Sesión de cableado end-to-end hacia pipeline 100% operativo.

### Added (resumen)
- **Schema v11** — `tbl_locf_cache`, `tbl_eventos_catalogo`, DDL self-expanding (`schema_parts/`)
- **LOCF persistente** — último valor real en DB si falla la API (`locf_store` + patch pipeline)
- **ONNX multi-agente** — mixin + train bootstrap/DB para alfa1/2, beta1/2, delta, omega
- **Juez 2h + agent_signals** — `register_cycle_predictions`: Padre + cada bot; `ventana_h` adaptativa
- **Launcher self-expanding** — `launcher_hex/h00..h11.hex` + cableado a `juez_cycle_register`
- **Omega dual-ask** — referencia por asertividad en el Padre
- **Telegram Centinela V2** — gate 30 min, credenciales solo por env
- **Volcado 24h** — telemetría viva → histórico en cascada
- **Dashboard** — pestañas Alfas / Betas / Omega / Padre / Juez / Eventos

### Changed / Fixed (resumen)
- Castigo/refuerzo del Juez a **todos** los bots (antes solo Padre)
- `ventana_h` ya no fija en 72 h (piso 2 h → lag empírico → tope 90 d)
- Cero sintéticos: NULL + LOCF en fallos de API
- Patrón self-expanding para archivos grandes (schema + launcher)

---

## [Unreleased]

### Fixed

- **`eodag` pin alineado a `>=4.0`.** `sentinel_omega/requirements.txt` pedía
  `eodag>=2.10` mientras que `pyproject.toml` pedía `>=4.0`; el mismatch podía
  instalar la API vieja (2.x: `search()` devolvía tupla `(results, count)` y
  usaba `productType=`). El código de `esa_sentinel.py` está escrito contra la
  API 4.x (`dag.search(collection="S2_MSI_L2A", …)`, resultado iterable), así
  que se sube el pin de `requirements.txt` a `>=4.0` para que coincida con
  `pyproject` y con el código. Verificado contra eodag 4.5: `search()` acepta
  `collection` vía kwargs y ya no expone `productType` — el uso de `collection=`
  es correcto.

- **Alfa-2 (y Júpiter) ahora aparecen en los reportes.** Los reportes armaban la
  tabla de bots desde `TBL_FIRMAS`, donde alfa2 no tiene filas (es live-only: sin
  backcast histórico, acumula desde `tbl_cobertura_satelital`) — por eso
  "desaparecía". `generar_reporte.py` ahora muestra a alfa2 y jupiter con su
  estado operativo aunque no tengan firmas; la fila de alfa2 **indica cuando
  falta el feed satelital** (0 pases → "instalar eodag + credenciales
  Copernicus"), señalando el pendiente de deployment. `reporte_sentinel.py`
  añade `jupiter` a `bots_order`; la prosa pasa de "6 bots" a "7 bots".

### Added

- **Júpiter como 7º agente del consenso** (`layers/geodynamic/jupiter/agent.py`):
  corroborador de atención colectiva. Emite WATCH/ALERT cuando hay tormenta
  geomagnética activa (Kp≥5) y/o el interés de búsqueda se dispara (≥2σ) con una
  correlación atención↔tormenta significativa. Registrado en el Padre en la
  familia `space_weather` (corrobora a Alfa-1/2 sin cambiar el conteo de familias
  del consenso), fuera de los pares senior/junior. Cableado no-bloqueante en el
  `layer_runner`; `fetch_jupiter_data` cachea Google Trends 6 h para no pegar el
  rate-limit en el loop en vivo.
- **Júpiter · Schumann + vocabulario ES/geo**: `schumann_series_from_trend()`
  alimenta la serie Schumann acumulada en la DB (`repository.schumann_trend`) a
  la correlación; el conector de Trends elige vocabulario español para
  `geo="MX"/"ES"` (`tormenta solar`, `aurora boreal`, …).
- **Júpiter — motor de correlación de tormentas solares** (`core/precursor/jupiter.py`):
  correlaciona **tormentas solares** (NOAA/GFZ Kp + GOES X-ray) contra la
  **atención colectiva** (Google Trends) y la **resonancia Schumann**. Reporta
  Spearman ρ + cross-correlation con lags (¿el interés de búsqueda sigue a la
  tormenta, y con cuántos días?). Solo tormentas solares.
  - Conector **Google Trends** (`infrastructure/api/google_trends.py`, `pytrends`):
    interés diario de vocabulario solar; degrada limpio ante rate-limit.
  - Conector **GFZ Potsdam Kp** (`infrastructure/api/gfz_kp.py`): Kp histórico
    largo (NOAA SWPC solo sirve ~7 días); CC BY 4.0.
  - Script `deploy/jupiter_correlaciones.py` → `estado/jupiter_correlaciones.json`.
  - Primer hallazgo real (ventana 90d): kp~xray ρ=+0.93 (p=0.003, físico);
    kp~Google-Trends ρ≈0 (sin correlación en la ventana). (+8 tests → 420.)

### Changed

- **Alfa-2 aprende su propio baseline por zona** (`alfa2/agent.py`): supera la
  limitación proxy-of-proxy documentada en v2.5.1. En vez de contar pases de
  satélite, mantiene una media/σ online por zona (Welford, persistible a
  `SNT_STATE_DIR`) sobre un índice térmico y puntúa cada ciclo como desviación Z
  sobre lo aprendido: |Z|≥2.5 → ALERT, ≥1.5 → WATCH. Alfa-2 deja de ser "ojo
  muerto" en el consenso de 6 agentes. Retrocompatible (thermal_anomaly_count
  sigue forzando ALERT; entrada vacía → NO_SIGNAL).

### Fixed

- **`esa_sentinel.py`**: `_get_dag()` ahora dentro del `try` de las búsquedas —
  un `eodag` ausente o credenciales inválidas degradan a resultado vacío en vez
  de propagar una excepción. (+3 tests de aprendizaje; suite 412.)

---

## [v2.5.0-complete] — 2026-07-15

Pipeline completado: delta_enriched integrado de punta a punta + rebuild_completo.py listo.

### Added

- **delta_enriched feature extraction** (`sentinel_omega/launcher.py`): `delta_cross_coupling`, `delta_geo_coupling`, `delta_schumann_coupling` ahora extraídas desde caché hacia vector de firma
- **Rebuild orchestration script** (`deploy/rebuild_completo.py`): pipeline de 8 pasos (parar → vaciar → migrar v6 → tuning → Fase 1+1b+2 → disciplina → VACUUM → reportes)
- **Complete end-to-end validation**: todas las features (alfa1, alfa2, beta1, beta2, delta, delta_cross) conectadas; reportes generan sin errores

### Fixed

- **Falsos ceros en features delta_cross** (`launcher.py`): si el fetch de
  delta_enriched falla, las features quedan AUSENTES (NaN, excluidas por
  similitud) en vez de escribir 0.0 falso — coherente con "cero datos sintéticos"

### Notes

- Fase 1b (multi-evento: sísmico + volcánico + solar + financiero) operativa
- Omega bot con ritmo cósmico integrado al entrenamiento
- Sistema 100% verificado de punta a punta; listo para producción

---

> **Historial anterior** (2026-07-11, 2026-07-05, 2026-07-04, honestidad total,
> cimática, correo, multi-evento, delta_enriched): conservado en el historial
> de commits de este archivo. Para el detalle de la sesión más reciente ver
> [`CHANGELOG_2026-08-19.md`](CHANGELOG_2026-08-19.md).
