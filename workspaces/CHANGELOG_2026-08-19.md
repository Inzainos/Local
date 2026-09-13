# Changelog session — 2026-08-19

Entrada canónica también referenciada desde `CHANGELOG.md`.

## [Unreleased] — 2026-08-19

Sesión de cableado end-to-end: ONNX, LOCF persistente, schema v11, Juez 2h,
agent_signals, Telegram Centinela, Omega dual-ask, catálogo multi-evento y
volcado 24h. Objetivo: pipeline a 100% funcionalidad operativa.

### Added

#### Schema v11 + LOCF persistente
- **`tbl_locf_cache`** — caché Last-Observation-Carried-Forward en DB
  (clave → payload JSON). Si una API falla, se reutiliza el último valor
  real observado; nunca se inventan datos sintéticos.
- **`locf_store.py`** + **`data_pipeline_locf_patch.py`** — `save_locf` /
  `load_locf` cableados al pipeline de ingestión.
- **`tbl_eventos_catalogo`** — catálogo unificado multi-evento (sismos,
  erupciones, tormentas solares, proxy tsunami).
- **`schema.py` self-expanding** — DDL comprimido en `schema_parts/*.b64`
  (zlib+base64) para evitar corrupción al subir archivos grandes por el
  conector; `SCHEMA_VERSION = 11`, ~35 tablas, hook `migrate_v11`.

#### ONNX multi-agente
- **`core/onnx_mixin.py`** — `try_load_onnx` / session / inference /
  `predict_signal` / `pad_vector` compartido por todos los bots.
- **`config/onnx_config.py`** — rutas y features por agente (incl. Omega,
  12 features espaciales).
- **`models/train_onnx_bootstrap.py`** y **`train_onnx_from_db.py`** —
  bootstrap + entrenamiento desde firmas + feedback del Juez
  (MultiOutputRegressor → `[confidence, signal_idx]`).
- Modelos ONNX para alfa1, alfa2, beta1, beta2, delta, omega.

#### Juez continuo + castigo por bot
- **`juez_cycle_register.py`** — `register_cycle_predictions(juez, geo, …)`:
  registra predicción del **Padre** y de **cada** entrada en
  `geo.agent_signals` (alfa/beta/delta/omega).
- **`ventana_h` adaptativa**: piso 2 h, lag de firma /
  `tbl_lag_anticipacion`, tope 90 días (sin corte artificial a 14 d ni 72 h
  fijas).
- Ritmo del Juez acortado a **cada 2 horas** (`RITMO_HORAS=2`) para
  aprendizaje constante (antes 72 h / 4 h según contexto).

#### Launcher self-expanding
- **`launcher.py`** se expande en runtime desde `launcher_hex/h00.hex` …
  `h11.hex` (zlib+hex). Incluye el cableado a
  `register_cycle_predictions` (agent_signals + ventana adaptativa).
- Documentación de parche: `LAUNCHER_AGENT_SIGNALS_PATCH.md`.

#### Omega dual-ask + referencia
- Protocolo dual-ask en el Padre: si Omega tiene mejor asertividad
  (`asertividad_omega >= corum`) actúa como referencia; el Padre pregunta
  al otro lado del consenso.
- Omega espacial sin sesgo Shadow DOM; consume telemetría de malla.

#### Telegram Centinela V2
- Alertas con gate 30 min (`_AlertGate`), credenciales solo por env,
  `dispatch_cycle_alerts` (threat / consensus / omega dual-ask / heartbeat).

#### Volcado 24h + cascada
- Telemetría viva → histórico cada 24 h (`mantenimiento.py`):
  `schumann_vivo` → `enjambre_telemetria` en cascada; tablas histórico
  duales + `persist_live_earthquakes`.

#### Dashboard por actores
- Pestañas Alfas / Betas / Omega / Padre / Juez / Eventos (métricas ONNX,
  mapas, multi-evento).

#### Dependencias
- `requirements.txt`: `ephem`, `onnxruntime` (además del resto del stack).

### Changed

- Registro de predicciones vivas: de solo-Padre con `ventana_h=72` a
  Padre + todos los bots con ventana empírica.
- LOCF: de in-memory a persistente en `tbl_locf_cache`.
- Schema: carga modular comprimida para integridad en pushes grandes.
- Pipeline `__init__.py`: exporta `register_cycle_predictions` y aplica
  parche LOCF al importar.

### Fixed

- Solo el Padre recibía castigo/refuerzo del Juez → ahora cada bot con
  señal en el ciclo se registra en `TBL_JUEZ_AUDITORIA`.
- `ventana_h` fija de 72 h desalineada del ritmo 2 h y de lags empíricos
  desde 1994.
- Stubs / PLACEHOLDER en archivos grandes al subir por el conector →
  patrón self-expanding (schema + launcher).
- Fallos de API rellenaban defaults sintéticos → NULL + LOCF del último
  valor real.

### Notes

- Archivos muy grandes (schema DDL, launcher, dashboard) viajan por
  chunks hex/b64; tras `git pull` el expander reconstruye el código
  en memoria al importar.
- Credenciales Telegram / SMTP solo por variables de entorno.
- Tras pull: `python -c "from sentinel_omega import launcher"` debe
  expandir sin error; verificar `register_cycle_predictions` en el
  código expandido.

---
