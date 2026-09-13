# AGENTS.md — Sentinel Omega

Guía operativa para agentes de IA que trabajen en este repositorio (Claude Code,
Cursor, Copilot, Codex, etc.). Es el archivo neutral que leen todas las
herramientas; `sentinel_omega/CLAUDE.md` tiene detalle adicional y
`sentinel_omega/README.md` la descripción completa del proyecto.

> Si editas archivos dentro de `sentinel_omega/`, ese `CLAUDE.md` aplica también.

## Qué es este repo

**Sentinel Omega** — plataforma de detección de **precursores de eventos
naturales** (sismos, actividad volcánica, tormentas solares, tsunamis).
Autor: Elán Zainos Corona (Fractal Core Research). Sucesor de la familia TITAN
V32/V46/V53.

Alcance: **únicamente precursores de eventos naturales.** No mezclar aquí:
- **Genómica** → va en el repo *SNT Genómica*.
- **Sentinel Titan** (lotería / "Elite") → va en otra rama, no en `main`.
- De lo financiero, este repo **sí** usa bolsa, cripto y tendencias (el bot
  `delta`, "el humor de la tierra") como una señal precursora más.

SNT (Shadow Node Theory) se usa **solo como framework matemático**
(ley de potencia `R(t) = a·t^b`), no como propósito del sistema.

## Estructura de alto nivel

```
sentinel_omega/     El sistema (6 agentes + Padre + Juez, pipeline, DB, dashboard)
deploy/             Operación: generar_reporte.py, systemd/Windows, atajo iOS, .env.example
estado/             Reportes publicados: REPORTE.md (último) + historial/AAAA/MM/ (versionado)
.github/workflows/  roy-vigilante.yml — corre un ciclo cada 2h en GitHub Actions (serverless)
```

## Comandos

```bash
# Tests — SIEMPRE desde la raíz del workspace, nunca desde dentro de sentinel_omega/
python -m pytest sentinel_omega/tests/ -q          # ~420 tests

# Un solo archivo
python -m pytest sentinel_omega/tests/test_firmas.py -v

# Sistema en vivo
python sentinel_omega/launcher.py                  # ciclo continuo (default 300s)
python sentinel_omega/launcher.py --once           # un ciclo y salir
python sentinel_omega/launcher.py --backcast        # carga histórica 1994-2025 (one-time)
python sentinel_omega/launcher.py --entrenar        # entrenamiento completo (sesgo PRE → 3 fases → cimática → sesgo POST)
python sentinel_omega/launcher.py --disciplina      # castigo desde abajo (menores M3.3-4.49)
python sentinel_omega/launcher.py --barrido         # compactación diaria + correlaciones + poda cimática
# Los flags de tarea corren la tarea y SALEN (no entran al ciclo continuo)
python sentinel_omega/shutdown.py                  # parar (SIGTERM, 30s → SIGKILL)
python sentinel_omega/reboot.py                    # stop + relaunch

# Juez: real vs predicción (ritmo auto-impuesto de 4h)
python deploy/verificacion_juez.py

# Reporte (los "ojos" del sistema; lo corre el vigilante tras cada ciclo)
python deploy/generar_reporte.py
python deploy/reporte_ejecutivo.py                 # plantilla ejecutiva (cada 6h)
python deploy/reporte_periodico.py --comparativo   # hoy vs ayer (o --semanal / --mensual)
python deploy/enviar_correos.py                    # despacho del outbox de correo

# Dashboard
streamlit run sentinel_omega/infrastructure/dashboard/app.py
```

## Reglas duras (no romper)

0. **REGLA CERO — nunca asumas, siempre revisa.** No des nada por hecho ni por
   conectado sin verificarlo contra el código y, cuando toque, **corriendo el
   flujo de punta a punta** (no basta con que pasen los tests unitarios).
   Antes de decir "ya está", compruébalo: ¿la tabla se pobló?, ¿el reporte lee
   la sección?, ¿el script corre sin error de verdad? Si no lo verificaste, no
   lo afirmes — di qué falta por comprobar. Esta regla manda sobre todas.
1. **Secretos solo por entorno.** Nunca hardcodear API keys/tokens. Usa
   `os.environ.get("NOMBRE", "")`. Los `.env` están en `.gitignore`; en CI van
   como GitHub Secrets. Las claves se rotan según se usan.
2. **Cero datos sintéticos.** Faltante = `NULL`. LOCF solo desde registros
   reales. El TEC derivado se etiqueta como *derived*, nunca como dato de sensor.
3. **`sentinel_omega/data/` está en `.gitignore`** — no existe en un checkout
   limpio (GitHub Actions). Crea la carpeta antes de abrir archivos ahí
   (`Path(...).parent.mkdir(parents=True, exist_ok=True)`).
4. **Reportes versionados, no sobrescritos.** `estado/REPORTE.md` es el último;
   cada corte se guarda en `estado/historial/AAAA/MM/` con hora local (UTC-6).
5. **Migración de esquema forward-only.** Columnas nuevas vía
   `EXPECTED_COLUMNS` / `_migrate_add_missing_columns`; no borrar columnas.
6. **Los tests deben pasar** antes de commitear cambios de código.

## Arquitectura (para ubicarte rápido)

6 agentes + Padre árbitro + Juez auditor (separado, nunca predice):

| Bot | Dominio | Entrenamiento |
|-----|---------|---------------|
| `alfa1` | Clima espacial: Bz, viento solar, Kp, protones/electrones | 30 años |
| `beta1` | Resonancia Schumann — **el latido**; todo se correlaciona contra él | 30 años |
| `alfa2` | Satélites ESA Sentinel | 14 años |
| `beta2` | Desgasificación volcánica / atmósfera (SO₂ sobre baseline natural) | 14 años |
| `delta` | Bolsa + cripto + tendencias | 10 años |
| `omega` | El ritmo cósmico: fase lunar/sicigias + Schumann + envolvente solar + acoplamiento Schumann↔mercado | 30 años |
| `padre` | Consenso jerárquico cruzado entre familias (aplica pesos) | — |

- **Familias:** `space_weather` (alfa1/alfa2), `schumann_cymatics` (beta1/beta2),
  `financial_sentiment` (delta). Consenso: ≥2 familias + ≥2 alertas +
  correlación Schumann > 0.3.
- **Firmas:** memoria de patrones por bot de la ventana de 14 días previa a cada
  evento. Estados `nueva → observada → recurrente → consolidada`; solo las
  consolidadas son exigibles.
- **Entrenamiento en 3 fases:** Fase 1 reconocimiento sísmico (sin castigo) → Fase 1b reconocimiento no sísmico (erupciones VEI≥3 + tormentas solares Kp≥6) → Fase 2
  disciplina (el Padre castiga; el Juez audita con severidad asimétrica —
  omitir un evento pesa 10× más que una falsa alarma). Tras las fases calcula la
  **matriz de correlaciones** feature × event_class, y el **sesgo de
  aprendizaje** se mide antes (línea base, sin castigo) y después
  (disciplinario) para reportar la mejora causal por bot.
- **Omega** no es un agente en vivo (no está en `layers/`): es un bot de
  memoria/correlación como contrapeso del Padre. Sus campos están mapeados de
  la telemetría existente en `BOT_FEATURES["omega"]` (sin fetchers propios);
  entrena en las mismas fases que los demás, y sus correlaciones viven en
  `tbl_correlaciones_omega` (umbral n≥30, patrón con Schumann y fase lunar),
  independientes de las del Padre. Reporte propio: `reporte_omega()`.
- **Pérdida asimétrica:** el sistema prefiere sobre-alertar a sub-alertar.

## Git y PRs

- Rama de desarrollo: **`claude/sentinel-omega-architecture-j3c2kn`**.
- No pushear a otra rama sin permiso explícito.
- Los PRs se abren como **draft**. Si un PR ya fue mergeado, no apiles trabajo
  nuevo encima: reinicia la rama desde `origin/main` y abre un PR nuevo.
- El cron de `roy-vigilante.yml` solo dispara en `main` → hay que mergear para
  activarlo.

## Fuentes de datos (todas públicas salvo donde se indica)

NOAA SWPC · USGS FDSN · NASA OMNI2 (backcast) · NASA MSVOLSO2L4 (SO₂ volcánico) ·
Tomsk (Schumann) · IERS (LOD) · Yahoo Finance (BTC, keyless) ·
OpenWeatherMap (`OPENWEATHERMAP_KEY`) · NASA NEO (`NASA_API_KEY`, fallback DEMO_KEY) ·
ESA Copernicus vía eodag.

## Alertas y reportes (canal: correo, Telegram en pausa)

Alertas y reportes viajan por email a `elan.zainos.corona@gmail.com` vía el
outbox `tbl_correo_salida` (fail-soft: sin `SMTP_USER`/`SMTP_PASS` quedan
PENDIENTES, nunca se fingen enviados). Rutinas del vigilante (hora MX=UTC-6):
ciclo del Padre cada 2 h · Juez verifica real vs predicción cada 4 h ·
reporte ejecutivo cada 6 h · comparativo diario 12am/12pm · semanal domingo
12:15pm · mensual fin de mes 12:30pm. La cimática
(`tbl_cimatica_patrones`) toma un snapshot de telemetría por ciclo: patrón
nuevo guarda todo, patrón repetido suma +1 a la frecuencia; cualquier
alta/incremento dispara la revisión del Padre y, si amerita, alerta por
correo.

## Telegram — consenso Padre (2026-09-03)

- **Digest horario SIEMPRE** (`TG_DIGEST_MINUTES=60`): concentrado Fantasma, muro, telemetría, precursores, loop. No saltar la hora.
- **Inmediato SOLO sin precedentes** (`is_unprecedented`): cimática NUEVO, firma nueva, muro kind nuevo, SYSTEM_DEAD. Precursores/firmas recurrentes → digest.
- Mini App: `TELEGRAM_WEBAPP_URL` = HTTPS público de `/mini` en el FastAPI del dashboard. No inventar túneles.
- Código: `infrastructure/messaging/consenso_vigilante.py`. `SENTINEL_DRY_RUN=1` no llama a la API de Telegram. No imprimir tokens.
