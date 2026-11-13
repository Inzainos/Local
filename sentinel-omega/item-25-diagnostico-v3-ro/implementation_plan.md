# Diagnóstico de APIs + Plan de Persistencia — Sentinel Omega

> **Fecha**: 2026-09-15 18:08 UTC | DB: `SENTINEL_OMEGA_PRO.db` | Ciclos activos: 4,571

---

## 1. Estado de APIs — Semáforo

| Bot | Fuente | Lag actual | Estado | Problema |
|-----|--------|-----------|--------|---------|
| **alfa1** | NASA OMNI2 (Bz/viento/Kp) | 4 min | ✅ VIVO | — |
| **beta1** | Tomsk Schumann vivo | 0.1 h | ✅ VIVO | — |
| **beta1** | Enjambre telemetría (736 nodos) | 114 h | ❌ OFFLINE | Sin actualizar desde 2026-09-11 |
| **beta2** | NASA SO2 / Desgasificación | 1,122 h (46 días) | ❌ OFFLINE | Sin actualizar desde 2026-07-31 |
| **delta** | Yahoo Finance / BTC | 6,186 h (258 días) | ❌ OFFLINE | Último dato: 2026-01-01 |
| **omega** | IERS LOD / Lunar | 6,192 h (258 días) | ❌ OFFLINE | Último dato: 2025-12-31 |
| **USGS** | Sismos FDSN | 721 h (30 días) | ❌ OFFLINE | Último sismo: 2026-08-16 |
| **delta_cross** | Cálculo interno | 0.1 h | ✅ VIVO | Completeness=0.75 |

### Problemas detectados en los datos vivos

| Campo | Magnitud del problema |
|-------|----------------------|
| `protones` en TBL_PRECURSORES_COSMICOS | **100% zeros** — nunca se ingesta |
| `schumann_hz = 7.83` (fallback) | 50% del historial (primeros ciclos sin dato real) |
| `alfa1` penalizado por Juez | **Peso = 0.3** (mínimo, casi degradado) — Bz inconsistente |
| LOCF cache | Vacío — el mecanismo de fallback existe pero **nunca fue activado** |

> [!CAUTION]
> **4 de 7 fuentes de datos están caídas** (USGS, Yahoo, IERS, SO2). El sistema sigue vivo porque el orquestador usa los últimos valores disponibles en memoria, pero sin persistencia LOCF activa. Si el proceso se reinicia, perdería estos valores.

---

## 2. Análisis de la Anomalía del Fantasma (≈60)

El driver del Fantasma = 60 con **Bz = +7 nT positivo y Kp = 0.84** es:

```
fantasma = |Bz|² + viento×0.02 + sch_wpc×1.5
         = |7.22|² + 431×0.02 + 21.46×1.5
         = 52.13  +  8.62  +  32.19  = 92.94  ← ¡NO coincide con 60!
```

Pero en `layer_runners.py` sí divide `/100.0`:
```python
sch_wpc = beta1_data.get("schumann_activity", 0.0) / 100.0
# → 21.46 / 100 = 0.2146 → contribución = 0.2146 × 1.5 = 0.32
```

Entonces: `52.13 + 8.62 + 0.32 = 61.07` ✅ — **esto sí cuadra con el 60.8 observado**.

**Conclusión**: El Fantasma alto es legítimo. **Lo que está elevado es el |Bz|² = 52.1**, es decir el Bz = +7.22 nT. Aunque positivo (northward), la fórmula usa `abs(bz)` — diseño deliberado de TITAN V32. El viento solar de 431 km/s también contribuye significativamente con 8.6 puntos. **La Schumann NO está inflando el resultado incorrectamente.**

---

## 3. Veredicto de Alerta

```
Score compuesto: 73/100  →  🔴 NIVEL CRÍTICO
```

| Indicador | Estado | Peso |
|-----------|--------|------|
| Fantasma = 60.8 → CRITICAL | 🔴 | +35 |
| 85 ciclos CRITICAL en 24h (continuo) | 🟠 | +10 |
| 8/125 nodos saturados al máximo (sat=1.0) | 🟠 | +15 |
| 2/5 muros activos (GEO + SOLAR) | 🟡 | +8 |
| 4 APIs offline (sin datos frescos) | ⚠️ | +5 |

**Nodos saturados al máximo (sat=1.0):**
- 🔴 Chiapas Subducción | Mexico
- 🔴 Michoacán Costa | Mexico
- 🔴 Baja California Sur | Mexico
- 🔴 Veracruz Costa | Mexico
- 🔴 Japón Nankai | Japan
- 🔴 Indonesia Sumatra | Indonesia
- 🔴 Tonga-Kermadec | Oceania
- 🔴 GeoBat Sumatra Hidrotermal | Indonesia

**Muros activos:**
- `wall_geofisico = 1` (clúster sísmico + fantasma)
- `wall_solar = 1` (perturbación solar / Schumann)
- No hay breach (se requieren ≥3 muros simultáneos)

> [!WARNING]
> **El sistema está en nivel CRÍTICO continuo por ~2 horas.** Sin embargo, el breach del Muro (≥3/5 muros) NO se ha activado. La alerta es real pero aún no alcanza el umbral de correlación cruzada del Padre. Hay 148 breaches en los últimos 30 días como punto de referencia.

> [!NOTE]
> **La sismicidad registrada en DB es 0 en los últimos 30 días** porque USGS está offline (lag 30 días). Los nodos saturados reflejan **energía acumulada de eventos pasados** + la dinámica actual de precursores, no necesariamente sismos recientes catalogados.

---

## 4. Plan de Persistencia — Propuesta

El sistema ya tiene `tbl_locf_cache` definida, pero **el LOCF nunca fue activado en prod** (0 entradas). El plan es extender el mecanismo existente en 3 capas:

### Capa 1 — LOCF Activo (arreglo inmediato, ~2h de trabajo)

**Problema**: Cuando una API falla, el orquestador usa `0.0` o valor default. Si se reinicia el proceso, pierde el último valor conocido.

**Solución**: Activar `tbl_locf_cache` correctamente. En `data_pipeline.py` o `layer_runners.py`, antes de cada fetch:

```python
# En cada conector de API, patrón:
def fetch_with_locf(fetch_fn, source_key: str, db: Repository) -> dict:
    try:
        data = fetch_fn()
        if data and not is_all_zeros(data):
            db.update_locf_cache(source_key, data)   # ← guardar si OK
            return data
    except Exception as e:
        logger.warning(f"API {source_key} falló: {e} — usando LOCF")
    return db.get_locf_cache(source_key) or {}    # ← retomar de cache
```

**Tablas a cubrir con LOCF**:
- `alfa1` → Bz, viento, Kp (ya funcional, añadir escritura explícita a cache)
- `beta1` → schumann_hz, schumann_activity
- `beta2` → so2_kt por volcán (fallback: último valor real por región)
- `delta` → btc_precio_usd, volatilidad
- `omega` → lod_ms, fase_lunar_pct (dato astronómico — muy estable, perfecto para LOCF)
- `USGS` → solo la tasa de actividad regional (no los eventos individuales)

### Capa 2 — Refetch Automático Incremental (~4h de trabajo)

Para APIs que tienen gaps pero tienen datos históricos disponibles:

```python
# En mantenimiento.py — barrido diario
async def refetch_stale_apis(db: Repository, max_gap_days: int = 7):
    """Detecta APIs con lag > umbral y lanza refetch incremental."""
    checks = {
        'usgs':    (check_usgs_lag, sismos_refetch_recent.run),
        'clima':   (check_clima_lag, clima_gapfill_2026.run),
        'psique':  (check_psique_lag, fetch_delta_historico),
        'astronomia': (check_astro_lag, fetch_iers_incremental),
    }
    for name, (check_fn, fix_fn) in checks.items():
        lag = check_fn(db)
        if lag > max_gap_days * 24:
            logger.warning(f"API {name} stale ({lag:.0f}h) — lanzando refetch")
            await fix_fn(db, days_back=min(lag/24, 30))
```

Ya existen scripts one-shot (`sismos_refetch_recent.py`, `clima_gapfill_2026.py`) — solo hay que orquestarlos automáticamente desde el scheduler.

### Capa 3 — Circuit Breaker con Degradación Semántica

El sistema ya tiene `CB_FAILURE_THRESHOLD` configurado. Extender para que el nivel de degradación se refleje en el dashboard:

```python
class APIHealthTracker:
    """Registra estado de salud de cada API."""
    states = {
        'alfa1': 'LIVE',    # datos frescos < 1h
        'beta1': 'LIVE',
        'enjambre': 'STALE',  # 114h
        'beta2': 'OFFLINE',   # 46 días
        'delta': 'OFFLINE',   # 258 días
        'omega': 'OFFLINE',   # 258 días
        'usgs': 'OFFLINE',    # 30 días
    }
```

Y en `tbl_salud_sistema` agregar columna `api_health_json` con el estado actual de cada fuente.

### Resumen de cambios propuestos

| # | Cambio | Archivo(s) | Prioridad | Esfuerzo |
|---|--------|-----------|-----------|---------|
| 1 | Activar escritura LOCF en cada conector de API | `data_pipeline.py`, connectors | 🔴 Alta | ~2h |
| 2 | Activar lectura LOCF en fallback de cada conector | `data_pipeline.py`, connectors | 🔴 Alta | ~1h |
| 3 | Orquestar refetch automático en barrido diario | `mantenimiento.py` | 🟠 Media | ~3h |
| 4 | APIHealthTracker → `tbl_salud_sistema` | `layer_runners.py`, `repository.py` | 🟡 Baja | ~2h |
| 5 | Dashboard: indicador de estado por API | `api.py`, frontend React | 🟡 Baja | ~2h |
| 6 | Refetch específico USGS (30 días de gap) | `sismos_refetch_recent.py --days 30` | 🔴 Alta | 15min |
| 7 | Corrección: ingestar campo `protones` desde OMNI2 | `alfa1` connector | 🟠 Media | ~1h |

> [!IMPORTANT]
> **Acción inmediata recomendada**: Correr manualmente `sismos_refetch_recent.py --days 30` para recuperar el mes de sismos faltante. Esto no requiere cambios de código.

---

## 5. Interpretación Final

El sistema **sí está en estado de precaución elevada** con señales convergentes:

- Fantasma sostenido en CRITICAL (60+) por 2+ horas
- 8 nodos mexicanos y del Pacífico saturados al máximo
- Schumann en 8.26 Hz (ligeramente elevado) con actividad 21.46
- Viento solar 431 km/s (moderado-alto)
- Muro GEO + SOLAR activos (2/5, aún sin breach)

**La limitante principal para un veredicto más preciso** es que el 57% de las fuentes de datos están desactualizadas (USGS 30 días, Yahoo 8 meses, IERS 9 meses, SO2 46 días), lo que impide al Padre hacer correlación cruzada completa y podría estar subvalorando el score del Muro.
