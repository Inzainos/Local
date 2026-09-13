# Sentinel Omega

Precursor detection platform for natural events.
Author: Elan Zainos Corona (Fractal Core Research)

## ⛔ REGLA #0 — nunca asumas, siempre revisa

No des nada por hecho ni por "conectado" sin verificarlo contra el código y,
cuando aplique, **corriendo el flujo de punta a punta** — que pasen los tests
unitarios NO prueba que el pipeline completo quede conectado. Antes de decir
"ya está": ¿la tabla se pobló?, ¿el reporte lee la sección?, ¿el script corre
sin error real? Si no lo verificaste, no lo afirmes; di qué falta comprobar.
Esta regla manda sobre todo lo demás.

## What this project does

Sentinel Omega detects **precursors of natural events** (earthquakes, volcanic activity, solar storms, tsunamis, etc.) using real-time geophysical data from NOAA, USGS, ESA, and other sources. It uses Shadow Node Theory (SNT) **only as the mathematical framework** (power law R(t) = a·t^b), not as the system's core purpose.

The system is the successor to the TITAN V32/V46/V53 bot family.

## Architecture — 8 Agents (SNT 5 + Omega + Loki + Padre), Single System

```
Orchestrator → GeodynamicLayerRunner → 8 Agents (SNT×5 + Omega + Loki) → Padre Consensus
│
├── Alfa-1 (Geodynamic: Bz, solar wind, seismic) — 30yr training
│       ↑ validates
├── Alfa-2 (Satellite: ESA Sentinel) — 14yr training
│
├── Beta-1 (The Artist — Cymatic Figure) — 30yr training  ← HEARTBEAT
│       ↑ validates
├── Beta-2 (The Analyst — réplica histórica + gas/presión) — 14yr training
│
├── Delta  (Fin stress — ALERT si combined>0.6) — 10yr training
│
├── Loki  (Fractal-Bayesiano: Gauss-Jordan→Fourier→Bayes, nodo Tlaxcala)
├── Omega  (Memoria/correlación: ritmo cósmico — luna, Schumann, envolvente
│           solar, acoplamiento Schumann↔mercado) — 30yr, NO es agente en vivo
│
└── Padre  (Hierarchical cross-family validator)
        ├── TITAN V32 Fantasma Risk Index
        ├── Precursor Scanner (15 types)
        └── Muro de los 5 Eventos
```

**Hierarchy**: #2 agents → report to #1 → Padre cross-validates across families.
**Schumann is the heartbeat**: Everything correlates against Schumann resonance (Beta-1).
If Schumann is perturbed alongside any other signal = precursor detected.

**Families**:
- `space_weather`: Alfa-1, Alfa-2
- `schumann_cymatics`: Beta-1, Beta-2
- `financial_sentiment`: Delta
- ` Correlation Alpha's Telemetry, Schumann Resonance, Delta and Beta's Patterns':Omega

**Consensus requires**: >= 2 families active + >= 2 alerts + schumann_correlation > 0.3

## Key formulas

- **Fantasma**: `(abs(bz)^2) + (viento*0.02) + (sch_wpc*1.5)` + pressure/Kp/LOD modifiers
- **Risk levels**: LOW (<5), MODERATE (5-15), HIGH (15-30), CRITICAL (>=30)
- **Asymmetric loss**: Miss penalty = 10x, False alarm = 1x
- **Beta-1 (honesto)**: FFT PLANO del Kp (`kp_spectral_features`) + Schumann
  MEDIDO de Tomsk (excitación >15% suma confianza; >30% con espectro calmo →
  WATCH). El viejo "filtro armónico"/coherencia era numerología y se eliminó.
- **Molchan**: ganancia = hit_rate ÷ tasa base (modelo nulo alertar-siempre,
  `core/precursor/baseline.py`). Ganancia ≤ 1 = sin habilidad real.
- **Pisos**: el sistema MIDE desde M3.3 (piso real del backcast); ALERTA solo
  desde M4.5 (solo el Padre avisa). `MIN_MAGNITUD_FIRMA=4.5`.
- **Vara de asertividad**: SOLO la vista `viva_real` (fase='viva', append-only);
  verdad POR FILA — ventana propia de 72h + nodos de la propia predicción.


## Dashboard (React Vite + FastAPI 8787)

- Dev:  Vite 6.4.3,  (.env local),  (WSL→Windows), proxy /api→8787. Build:  63 módulos 282KB/85KB gzip → dist/.
- API:  (946L) + 13 compat aliases sin /api (/health,/kpis,/telemetry/*,/consenso/*,/analysis/*,/agents/*,/system/*) — resuelven TBL_* reales + fallback. CORS para 5173/5174/4173.  envuelve  → {version, db:{connected,path}, agents}.
- Troubleshooting: ERR_CONNECTION_REFUSED en 5173 = host 127.0.0.1 en WSL; fix host 0.0.0.0. DB desconectada falso = health sin wrapper db.connected; fix health_alias. Launcher UnboundLocalError FormattedMessage = import mal scope; fix _FM2.

## Running tests

```bash
# From the workspace root (/home/user/workspaces):
python -m pytest sentinel_omega/tests/ -q

# Single test file:
python -m pytest sentinel_omega/tests/test_precursor.py -v
```

**Important**: Always run from `/home/user/workspaces/`, not from inside `sentinel_omega/`.

## Launcher / Shutdown / Reboot

```bash
# Launch orchestrator (continuous cycle mode)
python sentinel_omega/launcher.py

# Launch with dashboard + dry run (no Telegram)
python sentinel_omega/launcher.py --dashboard --dry-run

# Single cycle and exit
python sentinel_omega/launcher.py --once

# Historical backcast (one-time, 1994-2025)
python sentinel_omega/launcher.py --backcast

# Entrenamiento completo (sesgo PRE → Fase 1 + 1b → Fase 2 → lags →
# correlaciones → cimática histórica → sesgo POST)
python sentinel_omega/launcher.py --entrenar

# Disciplina de trasfondo (menores M3.3-4.49) y barrido diario
python sentinel_omega/launcher.py --disciplina
python sentinel_omega/launcher.py --barrido
# NOTA: los flags de tarea corren la tarea y SALEN (no entran al ciclo)

# Pasada del Juez (real vs predicción, ritmo auto-impuesto 4h)
python deploy/verificacion_juez.py

# Reportes periódicos con gráficas + despacho de correo
python deploy/reporte_periodico.py --comparativo   # (o --semanal / --mensual)
python deploy/enviar_correos.py

# Graceful shutdown (SIGTERM)
python sentinel_omega/shutdown.py

# Force shutdown (SIGKILL after 30s timeout)
python sentinel_omega/shutdown.py --force

# Reboot (stop + relaunch)
python sentinel_omega/reboot.py
python sentinel_omega/reboot.py --dashboard --dry-run
```

PID file: `data/sentinel_omega.pid`
Log file: `data/sentinel_omega.log`

## Rebuild Completo

Ejecuta reconstrucción de punta a punta: limpia memoria aprendida, migra DB v6, entrena Fase 1+1b+Fase 2, disciplina, VACUUM y genera reportes.

```bash
# Background run (recomendado)
nohup python deploy/rebuild_completo.py > estado/rebuild.log 2>&1 &

# Ver progreso en vivo
tail -f estado/rebuild.log
```

El script:
1. Para launcher (graceful SIGTERM)
2. Vacía: TBL_FIRMAS, pesos, correlaciones, orden, sesgo, lags, cimática (conserva backcast + Juez viva)
3. Migración DB v6 + índices + vistas
4. ANALYZE + PRAGMA optimize
5. Entrenamiento: Fase 1 (sísmico) + Fase 1b (volcánico+solar+financiero) + Fase 2 (disciplina) + lags + correlaciones
6. Disciplina de trasfondo + barrido diario (todos los cruces)
7. VACUUM + ANALYZE final
8. Reportes: generar_reporte.py + reporte_ejecutivo.py

Reporte final: `estado/REPORTE_REBUILD.md` (pesos, sesgo pre/post, firmas, rutas, tamaño DB).

## Running the dashboard

```bash
streamlit run sentinel_omega/infrastructure/dashboard/app.py
```

## Project structure

```
sentinel_omega/
├── orchestrator.py              # Master orchestrator — single runner cycle
├── config/sentinel_config.py    # Central config (secrets via os.environ)
├── core/
│   ├── shared/
│   │   ├── agent_base.py        # BaseAgent, PadreAgent, SignalType, ConsensusResult
│   │   ├── data_pipeline.py     # Pipeline base class
│   │   └── geometria_uvg.py     # Static UVG-125 Becker-Hagens matrix in RAM
│   ├── precursor/
│   │   ├── risk_calculator.py   # TITAN V32 fantasma formula
│   │   ├── scanner.py           # 15-type precursor scanner
│   │   ├── muro_cinco_eventos.py # 5-wall cross-correlation engine
│   │   ├── precursor_types.py   # Type registry + detection functions
│   │   └── assertivity.py       # V46 prediction tracking
│   ├── firmas/                  # Signature engine: per-bot pattern memory
│   │   └── signature_engine.py  # Extract/promote/match firmas (nueva→consolidada)
│   ├── juez/                    # Cold auditor, SEPARATE from Padre
│   │   └── juez.py              # ACIERTO/FALLO/FALSO_POSITIVO, recidivism severity
│   └── snt_engine/              # SNT math framework (satellization, friction, ASI, N-Body)
├── layers/
│   └── geodynamic/              # All 6 agents: alfa1, alfa2, beta1, beta2, delta,Omega, padre
├── infrastructure/
│   ├── api/                     # NOAA, USGS, Schumann, ESA, OWM, Crypto, Bolsa, Telegram
│   ├── pipeline/                # GeodynamicPipeline + GeodynamicLayerRunner + backcast
│   ├── database/                # SQLite schema, repository, 125-node seed
│   └── dashboard/               # Streamlit + Plotly dashboard (9 tabs)
├── data/                        # SQLite databases
└── tests/                       # 396 tests
```

> El repositorio raíz tiene un `AGENTS.md` (estándar neutral para cualquier
> agente de IA). Este `CLAUDE.md` es la guía específica de Claude Code y tiene
> prioridad para archivos dentro de `sentinel_omega/`.

## Security rules

- **NEVER hardcode API keys or tokens** — use `os.environ.get("KEY_NAME", "")`
- Keys will be rotated as used
- All secrets in `config/sentinel_config.py` use environment variables

## Environment variables

```
SMTP_USER             — Cuenta emisora de correo (app password de Gmail)
SMTP_PASS             — Contraseña de aplicación SMTP
SMTP_HOST / SMTP_PORT — Opcionales (default smtp.gmail.com:587)
CORREO_DESTINO        — Destinatario (default elan.zainos.corona@gmail.com)
TELEGRAM_BOT_TOKEN    — Telegram alert dispatch (en pausa: el canal es correo)
TELEGRAM_CHAT_ID      — Target chat for alerts (en pausa)
OPENWEATHERMAP_KEY    — Atmospheric data
BITSO_API_KEY         — Bitso exchange
BITSO_API_SECRET      — Bitso exchange
COINGECKO_API_KEY     — Market data
ALPHA_VANTAGE_KEY     — Stock market data
```

## Rutinas 24/7 (Roy Vigilante — GitHub Actions, hora MX = UTC-6)

- **Cada 2 h** — ciclo del Padre: status, registro de predicción viva
  (con SUS nodos) y snapshot cimático.
- **Cada 4 h** — el Juez verifica real vs predicción contra USGS (verdad
  por fila; ritmo auto-impuesto en `pipeline/verificacion.py`).
- **Cada 6 h** — reporte ejecutivo (se encola por correo).
- **12am y 12pm MX** — comparativo contra el día anterior (con gráfica).
- **Domingo 12:15pm MX** — reporte semanal (gráficas de fantasma/alertas/breaches).
- **Fin de mes 12:30pm MX** — reporte mensual.
- **Cada corrida** — despacho del outbox de correo (`deploy/enviar_correos.py`).

## Cimática y correo (sin Telegram)

- `tbl_cimatica_patrones` — snapshot del sistema por ciclo: patrón NUEVO →
  telemetría completa guardada; patrón existente → frecuencia+1 (contar,
  no anotar). Ámbito `general` o `nodo`; `event_class` cuando se conoce.
  Todo alta/incremento dispara la revisión del Padre; patrón nuevo con
  Padre activo o frecuencia consistente (≥3) con evento asociado → alerta
  por correo. Módulo: `core/firmas/cimatica.py`.
- `tbl_correo_salida` — outbox de ALERTAS y REPORTES a
  elan.zainos.corona@gmail.com. Envío SMTP fail-soft
  (`infrastructure/api/correo.py`): sin credenciales queda PENDIENTE,
  nunca se finge enviado.

## Database (SQLite)

Operational tables in `data/SENTINEL_OMEGA_PRO.db`:
- `TBL_PRECURSORES_COSMICOS` — Bz, viento, protones, Kp, LOD, Schumann, fase lunar, fantasma
- `TBL_NODOS_TOPOLOGIA` — 125 nodes (50 real + 50 ghost + 25 geobattery)
- `TBL_HISTORICO_SISMICO` — USGS seismic catalog
- `TBL_DETECCIONES` — Precursor detection log
- `TBL_CICLOS` — Orchestrator cycle history
- `TBL_MURO_EVENTOS` — Muro breach history

Learning/audit tables:
- `TBL_FIRMAS` — per-bot signature memory. Estado: nueva → observada → recurrente → consolidada (by recurrence). Only consolidadas are enforceable knowledge.
- `TBL_JUEZ_AUDITORIA` — Juez discipline ledger: ACIERTO / FALLO / FALSO_POSITIVO, asymmetric severity (miss of known firma = 20 base, miss = 10, false alarm = 1), recidivism-scaled. Columna `fase` ESTRICTA; fase viva append-only.
- `viva_real` (vista) — vara canónica de asertividad: solo fase='viva'.
- `TBL_PESOS_BOTS` — pesos de credibilidad [0.3, 1.5]; Padre paga doble.
- `tbl_firmas_menores` — disciplina de trasfondo (M3.3-4.49, temporal 90d).
- `tbl_correlaciones_padre` / `tbl_correlaciones_omega` — conteo patrón→evento (+1).
- `tbl_orden_precursores` / `tbl_orden_veredictos` — ¿el orden importa o es indiferente?
- `tbl_sesgo_aprendizaje` — realidad (causal) vs fantasía (in-sample) por bot.
- `tbl_cimatica_patrones` — snapshot de telemetría por ciclo: nuevo=telemetría completa, repetido=frecuencia+1; retro-etiquetado por eventos reales, poda del ruido a 30 días.
- `tbl_correo_salida` — outbox de alertas/reportes por email (fail-soft).
- `tbl_salud_sistema` / `tbl_resumen_diario` — bitácora por corte y barrido diario.

Backcast tables (1H resolution, 1994-2025):
- `tbl_clima_espacial_raw` — NASA OMNI2 (Bz, solar wind, Kp, proton flux)
- `tbl_astronomia_cinematica` — LOD, lunar phase, lunar distance, syzygy
- `tbl_historico_sismico_raw` — USGS seismic mapped to UVG-125 nodes
- `tbl_psique_financiera` — BTC price, volatility (2014+)
- `tbl_enjambre_telemetria` — Schumann resonance per node
- `tbl_nodo_estado_dinamico` — Node charge/tension (capped at 1.0)

Triggers: `trg_nodo_saturacion` + `trg_procesar_saturacion` cap saturation at 1.0

## Muro de los 5 Eventos

Five walls of cross-correlation. Breach when >= 3 walls active:

1. **GEOFISICO**: Seismic Cluster, Volcanico, Fantasma
2. **ATMOSFERICO**: Blue Jet, Sprite Rojo, Niebla Tule
3. **OCEANICO**: Tsunami, Huracan
4. **SOLAR/GEOMAGNETICO**: Tormenta Solar, Perturbacion, Schumann, Silent Trigger, GRB
5. **FINANCIERO/SOCIAL**: Correlacion Financiera

## Orchestrator cycle order

1. GeodynamicPipeline fetches data for all agents (alfa1, beta1, beta2, delta, alfa2)
2. Precursor risk computed (TITAN V32 fantasma)
3. Hurricane data fetched (non-blocking)
4. Scanner evaluates 15 precursor types
5. Muro evaluates 5-wall correlation
6. All agents ingest + analyze → signals
7. Padre evaluates consensus (hierarchical + Schumann correlation)
8. Alerts dispatched via Telegram

## Dashboard tabs

1. Precursor Risk — Fantasma gauge + waterfall + risk distribution
2. Muro 5 Eventos — Wall status cards + radar + activation timeline
3. Scanner — Detection table + type frequency + confidence stats
4. Topologia — World map 125 nodes + saturation ranking
5. Sismico — Seismic map + depth vs magnitude + region charts
6. Schumann — Frequency trend + activity + Hz vs WPC scatter
7. Layer Signals — Agent consensus per layer
8. SNT Analysis — Satellization exponent + power law fits
9. Ciclos — Timeline + alert/breach rate gauges

## Branch

All development on: `claude/sentinel-omega-architecture-j3c2kn`

## Telegram (consenso Padre, 2026-09-03)

Canal Telegram ya no dispara cada ciclo. El Padre (`consenso_vigilante.py`):

1. **Reporte horario siempre** (`TG_DIGEST_MINUTES=60`) — Fantasma+nivel, muro n/5, telemetría, top precursores, loop, botón Mini App (`TELEGRAM_WEBAPP_URL` HTTPS público a `/mini`). No se omite la hora en calma. No es un pile de "precursores revisar".
2. **Page inmediato solo si no hay registro** (`is_unprecedented`): patrón cimática NUEVO, firma `TBL_FIRMAS` nueva, tipo de muro no visto, `SYSTEM_DEAD`. Firmas recurrentes y watches de precursores van al digest. Rojo/naranja rutinario NO pagina.
3. Correo (`tbl_correo_salida`) no cambia. `SENTINEL_DRY_RUN=1` no envía. Mini App exige HTTPS; este repo no crea túnel.
