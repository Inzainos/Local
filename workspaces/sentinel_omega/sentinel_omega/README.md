# Sentinel Omega v2.5.4 — The Third Act

**Plataforma de detección de precursores de eventos naturales**

Sentinel Omega monitorea en tiempo real datos geofísicos, atmosféricos, solares, oceánicos y financieros para detectar precursores de terremotos, erupciones volcánicas, tormentas solares, tsunamis y otros eventos naturales de alto impacto.

> Sucesor de la familia de bots TITAN V32/V46/V53.
> Autor: Elán Zainos Corona — Fractal Core Research

---

## Objetivo del Proyecto

El sistema busca resolver un problema fundamental: **detectar señales precursoras de eventos naturales con suficiente anticipación para permitir alertas tempranas**. A diferencia de los sistemas de alerta sísmica convencionales que solo reaccionan después del evento, Sentinel Omega monitorea correlaciones multi-dominio (geofísico, atmosférico, solar, oceánico y financiero) para identificar patrones que históricamente preceden a eventos de gran magnitud.

La plataforma integra datos de 10+ fuentes públicas en tiempo real y aplica un framework de consenso jerárquico donde agentes especializados votan con pérdida asimétrica: el costo de no detectar un evento (miss) se penaliza 10x más que una falsa alarma.

---


## Dashboard local (React Vite) — acceso y troubleshooting

- **Dev (Vite)**:  → http://127.0.0.1:5173 (también http://localhost:5173).  debe tener  y ; sin  Windows ve ERR_CONNECTION_REFUSED por aislamiento WSL.
- **API prod**:  (CORS para 5173/5174).  devuelve  — .
- **Prod estático fallback**:  →  282KB/85KB gzip (sin vite dev).
- **Health check**:  debe ser true; <!doctype html>
<html lang="es" class="dark">
  <head>
    <script type="module">import { injectIntoGlobalHook } from "/@react-refresh";
injectIntoGlobalHook(window);
window.$ = () => {};
w debe devolver .

## Hallazgos e Innovación

### 1. Fórmula Fantasma (TITAN V32)

El índice Fantasma es una función compuesta que correlaciona variables solares, geomagnéticas y atmosféricas para producir un score de riesgo precursor:

```
fantasma = (abs(Bz)^2) + (viento x 0.02) + (Schumann_WPC x 1.5)

Modificadores post-core:
  + Presión atmosférica (< 1008 hPa -> hasta +3.0)
  x Kp storm (>= 5 -> hasta x1.5)
  + LOD anomaly (> 0.5 ms -> hasta +2.0)
```

**Hallazgo**: La componente cuadrática del Bz (campo magnético interplanetario norte-sur) es el predictor más fuerte. Valores de Bz < -10 nT generan contribuciones Bz^2 > 100 puntos, disparando directamente el umbral CRITICAL. Esto se alinea con la observación empírica de que perturbaciones geomagnéticas severas (Bz fuertemente negativo) preceden actividad sísmica inusual en ventanas de 48-96 horas.

| Nivel    | Rango   | Interpretación                                   |
|----------|---------|--------------------------------------------------|
| LOW      | < 5     | Actividad de fondo normal                        |
| MODERATE | 5 - 15  | Señales elevadas, monitoreo activo               |
| HIGH     | 15 - 30 | Precursores múltiples, alerta preventiva         |
| CRITICAL | >= 30   | Correlación multi-dominio, alerta inmediata      |

### 2. Espectro Kp plano + Schumann MEDIDO (Beta-1, honesto desde v2.5.1)

El agente Beta-1 combina dos observaciones independientes:

- **FFT plano del Kp** (`kp_spectral_features`): energía total, ratio de alta
  frecuencia y periodo dominante del espectro geomagnético — sin disfraz de
  resonancia. (El "filtro armónico Schumann" anterior era físicamente
  imposible: 7.83 Hz está ~5 órdenes de magnitud sobre el Nyquist del Kp
  muestreado a 3 h, la "coherencia" salía ≈1 siempre. Se eliminó.)
- **Schumann MEDIDO de Tomsk**: frecuencia y % de actividad reales de la
  estación. Excitación medida > 15% suma confianza; > 30% con espectro Kp
  calmo produce WATCH — porque es una observación, no un artefacto.
- **Correlación Tierra-Luna** solo con ≥ 3 ciclos lunares completos en la
  ventana (dos series suaves en ventana corta dan |r| alto por azar); con
  menos, se reporta `None` y jamás alimenta confianza.

**Hallazgo (el que sí sobrevive a la física)**: la correlación entre
excitaciones anómalas MEDIDAS en la resonancia Schumann de Tomsk y actividad
sísmica significativa 48-72 horas después.

### 3. Muro de los 5 Eventos (Correlación Cruzada Multi-Dominio)

La innovación central es que ningún precursor individual es confiable — es la **correlación simultánea** de múltiples dominios lo que indica riesgo real:

| Muro | Dominio             | Precursores                                    |
|------|---------------------|------------------------------------------------|
| 1    | GEOFÍSICO           | Enjambre Sísmico, Volcánico, Fantasma          |
| 2    | ATMOSFÉRICO         | Blue Jet, Sprite Rojo, Niebla Tule             |
| 3    | OCEÁNICO            | Tsunami, Huracán                               |
| 4    | SOLAR/GEOMAGNÉTICO  | Tormenta, Perturbación, Schumann, Silent, GRB  |
| 5    | FINANCIERO/SOCIAL   | Correlación Financiera                         |

**Breach**: Cuando >= 3 muros están activos simultáneamente, el sistema declara un "breach" — indicando que múltiples dominios independientes están correlacionados, lo cual históricamente precede eventos significativos.

**Hallazgo**: La inclusión del muro FINANCIERO/SOCIAL es innovadora. Se observan correlaciones entre caídas abruptas en mercados financieros (VIX spike, crypto fear index alto, bolsa bearish) y eventos naturales dentro de ventanas de 72 horas. La hipótesis es que mercados sensibles capturan información agregada (comportamiento de aseguradoras, contratos de reaseguro, posiciones de commodities agrícolas) que anticipa disrupciones.

### 4. Silent Trigger (Calma Precursora)

**Hallazgo contra-intuitivo**: Períodos de calma geomagnética extrema (todos los valores de Kp < 2.0 sostenidos por 24+ horas) son precursores tan significativos como las tormentas. El "Silent Trigger" detecta esta calma anómala. La ausencia de perturbación es, en sí misma, una señal.

### 5. Topología de 125 Nodos con Saturación

El sistema modela la Tierra completa con una malla de 125 nodos de monitoreo basada en la geometría UVG Becker-Hagens:

| Tipo        | Cantidad | Descripción                                    |
|-------------|----------|------------------------------------------------|
| Real        | 75       | Zonas sísmicas reales (Ring of Fire global + México) |
| Ghost       | 50       | Nodos fantasma inferidos de gaps sísmicos      |
| Geobattery  | 25*      | Zonas de acumulación electroquímica (incluidas en los 75 reales) |

*Distribución DB real: 75 reales + 50 Ghost = 125 UVG. Los 25 Geobattery están modelados como subconjunto de los reales (conductividad >0), no como nodos adicionales. Total físico = 125.

**Hallazgo**: Los nodos "ghost" — posiciones inferidas donde no hay monitoreo pero la topología sugiere acumulación de estrés — han mostrado ser zonas de riesgo subestimado por redes sísmicas convencionales. Los nodos "geobattery" modelan zonas donde corrientes telúricas y diferencias de potencial electroquímico en el subsuelo pueden actuar como acumuladores de energía. La saturación de un nodo (capped a 1.0 por trigger SQL) indica zona de máximo estrés acumulado.

La matriz estática UVG-125 se carga en RAM al importar (`geometria_uvg.py`) y permite mapear cada sismo global al nodo más cercano. Tlaxcala (19.31, -98.24) es el nodo de observación (id=0); los otros 125 cubren el planeta. Con 125 nodos y radio de 5°, la dispersión ya es nodal y global — por eso la línea base de Molchan es 16% (casi toda ventana tiene un sismo cerca de algún nodo); la ganancia real debe medirse específica por nodo, no solo global.

### 6. Pérdida Asimétrica en Consenso Jerárquico

El Padre usa pérdida asimétrica en el consenso:

```
Costo de miss   = 10 x peso_base
Costo de falsa  =  1 x peso_base
```

**Innovación**: El sistema prefiere sobre-alertar a sub-alertar. Un 10% de falsas alarmas es aceptable si el sistema captura el 95% de eventos reales. Esto invierte la lógica de la mayoría de sistemas de alerta que optimizan para minimizar falsas alarmas.

### 7. Validación de Asertividad (V46 Lineage) + Línea Base de Molchan

El tracker de asertividad compara predicciones contra eventos reales del catálogo USGS usando distancia euclidiana dentro de un radio de 5 grados:

- **Hit rate**: Predicciones confirmadas por eventos M>=4.5
- **Miss rate**: Eventos que no fueron predichos
- **False alarm rate**: Predicciones sin evento correspondiente

**Honestidad estadística (v2.5.1)**:
- **Verdad POR FILA**: cada predicción viva se resuelve contra los eventos de
  SU ventana de 72 h y los **nodos de la propia predicción** (un aviso solo
  vale si acierta DÓNDE avisó); los silencios se juzgan contra toda la malla.
- **Línea base de Molchan** (`core/precursor/baseline.py`): un modelo nulo que
  alerta SIEMPRE tiene como hit-rate la tasa base de sismicidad. El sistema
  reporta su **ganancia** (hit-rate ÷ tasa base) en cada corte — ganancia ≤ 1
  significa que el número bonito es geografía, no predicción.
- Solo la fase **viva** puntúa asertividad (vista `viva_real`); el
  entrenamiento es bitácora y no se mezcla.

### 8. Cimática — memoria de patrones destilada por eventos

Cada ciclo toma un **snapshot** de la telemetría (huella de bandas
logarítmicas) en `tbl_cimatica_patrones`: patrón nuevo → telemetría completa
guardada; patrón repetido → frecuencia+1. Cuando el Juez confirma un evento
real, los patrones de su víspera se **retro-etiquetan** con lo que desataron;
el patrón que tras 30 días nunca se asoció a un evento es ruido y se **poda**.
La tabla converge sola a la cimática real de cada tipo de evento (por nodo y
general). El histórico de 30 años la pre-puebla vía `entrenar_cimatica()`.

---

## Arquitectura — 6 Agentes, Sistema Único

```
Orchestrator -> GeodynamicLayerRunner -> 6 Agentes -> Consenso del Padre
|
+-- Alfa-1 (Geodinámico: Bz, viento solar, sísmico) — 30 años entrenamiento
|       ^ valida
+-- Alfa-2 (Satélite: ESA Sentinel) — 14 años
|
+-- Beta-1 (Schumann / cimática / energía liberada) — 30 años  <- LATIDO
|       ^ valida
+-- Beta-2 (Química atmosférica) — 14 años
|
+-- Delta  (Financiero: crypto + bolsa + humor de la tierra) — 10 años
|
+-- Padre  (Validador jerárquico cruzado entre familias)
        +-- Índice de Riesgo Fantasma TITAN V32
        +-- Scanner de Precursores (15 tipos)
        +-- Muro de los 5 Eventos
```

**Jerarquía**: Los agentes #2 reportan al #1 -> el Padre valida entre familias.
**Schumann es el latido**: Todo se correlaciona contra la resonancia Schumann (Beta-1).
Si Schumann está perturbado junto con cualquier otra señal = precursor detectado.

**Familias**:
- `space_weather`: Alfa-1, Alfa-2
- `schumann_cymatics`: Beta-1, Beta-2
- `financial_sentiment`: Delta

**El consenso requiere**: >= 2 familias activas + >= 2 alertas + correlación_schumann > 0.3

### Ciclo del Orquestador

1. **GeodynamicPipeline** obtiene datos para todos los agentes (alfa1, beta1, beta2, delta, alfa2)
2. **Fantasma V32** calcula el riesgo precursor de las señales crudas
3. **Datos de huracán** se obtienen (non-blocking)
4. **Scanner** evalúa los 15 tipos de precursor contra los datos del ciclo
5. **Muro de los 5 Eventos** evalúa la correlación de 5 dominios
6. Todos los agentes ingestan + analizan -> señales
7. **Padre** evalúa el consenso (jerárquico + correlación Schumann)
8. Las alertas se despachan vía Telegram + registro en SQLite

### Señales del Sistema

| Señal     | Significado                           | Uso                     |
|-----------|---------------------------------------|-------------------------|
| BULLISH   | Tendencia alcista (mercados)          | Delta (financiero)      |
| BEARISH   | Tendencia bajista (mercados)          | Delta (financiero)      |
| NEUTRAL   | Sin tendencia clara                   | Todos los agentes       |
| WATCH     | Excitación coherente, monitorear      | Beta-1 (Schumann)       |
| ALERT     | Precursor confirmado, alertar         | Geodinámico             |
| NO_SIGNAL | Sin datos o sin análisis              | Todos los agentes       |

---

## 15 Tipos de Precursor

| #  | Tipo                     | Muro               | Ventana | Variables Clave                       |
|----|--------------------------|---------------------|---------|---------------------------------------|
| 1  | Resonancia Schumann      | Solar/Geomagnético  | 72h     | schumann_hz, activity_pct             |
| 2  | Silent Trigger (Calma)   | Solar/Geomagnético  | 48h     | kp_values (todos < 2.0 por 24h)      |
| 3  | Enjambre Sísmico         | Geofísico           | 48h     | event_count, max_mag, cluster_radius  |
| 4  | Blue Jet                 | Atmosférico         | 72h     | humidity, temp, pressure, weather_id  |
| 5  | Sprite Rojo              | Atmosférico         | 72h     | humidity, pressure, weather_id (211)  |
| 6  | Niebla Tule              | Atmosférico         | 72h     | humidity, temp, visibility, wind      |
| 7  | Tormenta Solar           | Solar/Geomagnético  | 96h     | xray_flux (>= 1e-5 W/m2 = M-class)   |
| 8  | Perturbación Geomag.     | Solar/Geomagnético  | 96h     | kp_mean (>= 5.0 = storm level)       |
| 9  | Huracán                  | Oceánico            | 120h    | distance_km, category                 |
| 10 | Tsunami                  | Oceánico            | 24h     | magnitude, depth (>= 7.0, < 70km)    |
| 11 | Inferencia ML            | —                   | 48h     | onnx_model_output                     |
| 12 | Gamma-Ray Burst          | Solar/Geomagnético  | 168h    | xray_flux (>= 1e-4 W/m2)            |
| 13 | Precursor Volcánico      | Geofísico           | 72h     | so2_index, seismic_coupling           |
| 14 | Índice Fantasma          | Geofísico           | 72h     | fantasma composite score              |
| 15 | Correlación Financiera   | Financiero/Social   | 72h     | fear_greed, vix, btc_change           |

---

## Framework Matemático (SNT)

Sentinel Omega utiliza la **Shadow Node Theory** exclusivamente como framework matemático — no como propósito del sistema. El modelo de ley de potencia describe relaciones de dominancia/subordinación en sistemas complejos:

```
R(t) = a * t^b
```

| Régimen              | Exponente b | Interpretación                             |
|----------------------|-------------|--------------------------------------------|
| Extreme              | > 2.0       | Satelización sin fricción                  |
| Roche Radius         | > 1.0       | Satelización rápida (punto de no retorno)  |
| Active               | > 0.3       | Satelización activa                        |
| Gradual              | > 0.05      | Satelización gradual                       |
| Equilibrium          | > -0.1      | Estado estable                             |
| Convergence/Leapfrog | <= -0.1     | Desacoplamiento / convergencia             |

Se aplica a:
- Ratios de dominancia financiera (BTC/ETH, SPY/QQQ)
- Intensidad geomagnética (tendencias de Kp)
- Gradientes de nodos topológicos

---

## Base de Datos (SQLite)

### Tablas Operacionales

6 tablas en `SENTINEL_OMEGA_PRO.db` con modo WAL y foreign keys (schema v6):

| Tabla                    | Registros   | Propósito                                              |
|--------------------------|-------------|--------------------------------------------------------|
| TBL_PRECURSORES_COSMICOS | Por ciclo   | Snapshot: Bz, viento, protones, Kp, LOD, Schumann, fantasma, fase lunar |
| TBL_NODOS_TOPOLOGIA      | 125 fijos   | Nodos N-Body con conductividad, energía, saturación    |
| TBL_HISTORICO_SISMICO    | Acumulativo | Catálogo USGS con deduplicación por event_id           |
| TBL_DETECCIONES          | Por ciclo   | Log de precursores detectados con tipo, confianza, JSON |
| TBL_CICLOS               | Por ciclo   | Historial de ciclos: señal, consenso, riesgo, muro     |
| TBL_MURO_EVENTOS         | Por breach  | Breaches del Muro con correlación y muros activos      |

### Tablas de Aprendizaje y Auditoría

| Tabla                      | Propósito                                                        |
|----------------------------|-------------------------------------------------------------------|
| TBL_FIRMAS                 | Memoria de patrones por bot. Estado: nueva → observada → recurrente → consolidada (por recurrencia). Solo las consolidadas son conocimiento exigible. |
| TBL_JUEZ_AUDITORIA         | Ledger disciplinario del Juez: ACIERTO / FALLO / FALSO_POSITIVO con severidad asimétrica (omitir firma conocida = 20 base, omisión = 10, falsa alarma = 1) escalada por reincidencia. Columna **`fase`** estricta (viva/reconocimiento/backtest/observacion/trasfondo); la fase viva es **append-only**. |
| **viva_real** (vista)      | Vara canónica de asertividad: SOLO filas `fase='viva'`. Todas las tuberías de reporte puntúan desde aquí. |
| TBL_PESOS_BOTS             | Pesos de credibilidad por bot [0.3, 1.5] — castigo multiplicativo (Padre paga doble), refuerzo recupera hasta 1.0. |
| tbl_firmas_menores         | Disciplina de trasfondo: firmas TEMPORALES de sismos M3.3–4.49 (retención 90 días, solo sobreviven los pesos). |
| tbl_eventos_no_sismicos    | Catálogo derivado de erupciones volcánicas (VEI≥3) y tormentas solares (Kp≥6 onset). Alimenta la Fase 1b de entrenamiento multi-evento. |
| tbl_patrones_correlacion   | Matriz feature × event_class calculada tras el entrenamiento. Para cada par guarda media, media global y ratio; ratio > 1 significa que la variable está elevada en los 14 días previos a ese tipo de evento. |
| tbl_correlaciones_padre / _omega | Conteo de patrones → clase de evento (+1 por ocurrencia, sin anotar cada una). Cuantifican p. ej. el Silent Trigger. |
| tbl_orden_precursores / _veredictos | El Padre ve el ORDEN de los precursores en la víspera y discierne contando si la secuencia importa o es indiferente. |
| tbl_sesgo_aprendizaje      | Realidad vs fantasía por bot: reconocimiento causal (memoria ANTERIOR al evento) vs in-sample. Medido PRE (sin castigo) y POST (con castigo) en cada entrenamiento. |
| **tbl_cimatica_patrones**  | Snapshot de telemetría por ciclo (huella de bandas logarítmicas). Patrón nuevo = telemetría completa; repetido = frecuencia+1. Retro-etiquetado por eventos reales y poda del ruido (30 días de gracia). |
| **tbl_correo_salida**      | Outbox de ALERTAS y REPORTES por email (fail-soft: sin SMTP quedan PENDIENTES). |
| tbl_salud_sistema          | Bitácora por corte: versión, pesos, asertividad viva, deltas. |
| tbl_resumen_diario         | Barrido diario: lo compactado no se pierde, se resume. |

**Entrenamiento en tres fases** (`--entrenar`):
- **Fase 1** — Reconocimiento sísmico (sin castigo): extrae la ventana de 14 días previa a cada evento M5+ del backcast y la registra como firma por bot.
- **Fase 1b** — Reconocimiento no sísmico: igual proceso sobre erupciones volcánicas (VEI≥3) y tormentas solares (Kp≥6) derivadas de las tablas de backcast. Los bots aprenden qué precede a estos eventos además de los sísmicos.
- **Fase 2** — Disciplina: re-presenta las firmas consolidadas; el Juez castiga si el sistema ya no las reconoce.
- Al finalizar, calcula la **matriz de correlaciones** (feature × event_class) y la almacena en `tbl_patrones_correlacion` para el reporte de mapa de calor.

En operación, cada ciclo compara el estado vivo contra las firmas consolidadas ("el estado actual se parece 87% al que precedió el M7 del nodo 45").

### Tablas de Backcast Histórico (resolución 1H, 1994-2025)

| Tabla                      | Clave Primaria          | Propósito                                    |
|----------------------------|-------------------------|----------------------------------------------|
| tbl_clima_espacial_raw     | timestamp_blk           | NASA OMNI2: Bz, viento solar, Kp, protones  |
| tbl_astronomia_cinematica  | timestamp_blk           | LOD, fase lunar, distancia lunar, sicigia    |
| tbl_historico_sismico_raw  | (timestamp_blk, id_nodo)| Sismos USGS mapeados a nodos UVG-125        |
| tbl_psique_financiera      | timestamp_blk           | BTC precio, volatilidad (2014+)              |
| tbl_enjambre_telemetria    | (timestamp_blk, id_nodo)| Resonancia Schumann por nodo                 |
| tbl_nodo_estado_dinamico   | (timestamp_blk, id_nodo)| Carga/tensión por nodo (cap 1.0 vía trigger) |

### Tablas de Live-Only (acumuladas desde ciclos en vivo)

| Tabla                   | Clave Primaria            | Propósito                                         |
|-------------------------|---------------------------|---------------------------------------------------|
| tbl_cobertura_satelital | id (autoincrement)        | Cobertura satelital ESA Sentinel-2 por zona/ciclo |
| tbl_delta_cross         | id (autoincrement)        | Resultados de correlación cruzada geofísico-financiera por ciclo |

**Protocolo de backcast**: CERO datos sintéticos. Faltante = NULL. LOCF solo desde registros reales.

**Triggers**: `trg_nodo_saturacion` y `trg_procesar_saturacion` — cap automático de saturación/carga a 1.0.

---

## Dashboard — React (v2.5.4, puerto 5173→8787) + Streamlit legacy (11 pestañas, puerto 8510)

**v2.5.4 — Dashboard React** (6 tabs: Principal/Telemetría/Consenso/Análisis/Agentes/Sistema, React+shadcn, API FastAPI ) + **Streamlit legacy** (11 pestañas, ) con datos en tiempo real:

| Tab | Nombre          | Visualizaciones                                                                                      |
|-----|-----------------|------------------------------------------------------------------------------------------------------|
| 1   | Precursor Risk  | Gauge fantasma, historial, waterfall de componentes, donut de riesgo, **timeline 50 ciclos con bandas 15/30 + vista previa Telegram con PNG** |
| 2   | Muro 5 Eventos  | 5 tarjetas de estado, radar de correlación, timeline de activación                                  |
| 3   | Scanner         | Tabla de detecciones, barras por tipo, histograma de confianza, stats                                |
| 4   | Topología       | Mapa mundial 125 nodos, ranking saturación, conductividad vs energía                                |
| 5   | Sísmico         | Mapa sísmico, histograma magnitudes, profundidad vs magnitud, regiones                              |
| 6   | Schumann        | Tendencia Hz, actividad WPC, distribución, Hz vs actividad scatter                                  |
| 7   | Layer Signals   | Consenso por capa, señales de agentes individuales                                                   |
| 8   | SNT Analysis    | Exponente de satelización, fits de ley de potencia                                                   |
| 9   | Ciclos          | Timeline fantasma + precursores, tasa de alertas, breach rate gauges                                |
| 10  | Cimatica (v2.5.3) | **Barras top-10 patrones por frecuencia, tabla 20 mas frecuentes, pie por clase, PNG Telegram** |
| 11  | Agente          | Estado del agente, logs, controls                                                                   |

**Novedades v2.5.3:**
- `render_cimatica()`: 3 metricas (total/consistentes/clases), barras `plotly_dark` con `px.bar`, tabla `patron_id|clave|frecuencia|clase|ambito|nodo|ultima_vez` (20), pie `por_clase`, boton "Generar PNG cimatica (como Telegram)" via `cimatica_bars()`.
- `render_precursor_risk()` enriquecido: `_render_fantasma_timeline_plotly()` (50 ciclos, `go.Scatter` + `add_hrect` 0-15/15-30/30+, `add_hline` 15/30) + tabla 10 + boton "Vista previa alerta Telegram" (`AlertTemplates.centinela_advertencia` + `fantasma_timeline` PNG).
- `repository.py`: `cimatica_top_patrones()`, `cimatica_stats()`, `fantasma_timeline()` - queries `tbl_cimatica_patrones` / `tbl_salud_sistema`.

---

## Fuentes de Datos (APIs)

| Fuente           | Datos                                     | Auth      | Uso                  |
|------------------|-------------------------------------------|-----------|----------------------|
| NOAA SWPC        | Bz, viento solar, Kp, GOES X-ray, protones | Público   | Alfa-1, Scanner      |
| USGS FDSN        | Catálogo sísmico mundial                   | Público   | Scanner, Asertividad |
| NASA OMNI2       | Bz, viento solar, Kp históricos (backcast) | Público   | Backcast             |
| Tomsk SRF        | Resonancia Schumann (7.83 Hz)              | Público   | Beta-1, Scanner      |
| IERS             | Length-of-Day (LOD)                        | Público   | Fantasma             |
| ESA Copernicus   | Sentinel-1 SAR, Sentinel-2 multispectral   | Público   | Alfa-2, Beta-2       |
| OpenWeatherMap   | Presión, temp, humedad, weather_id          | API Key   | Beta-2, Scanner      |
| NOAA NHC         | Ciclones tropicales activos                 | Público   | Scanner (huracanes)  |
| CoinGecko        | Dominancia BTC, market caps                 | Público   | Delta                |
| Yahoo Finance    | OHLCV acciones, VIX, ETFs                  | Público   | Delta                |

---

## Estructura del Proyecto

```
sentinel_omega/
├── launcher.py                          # Launcher — arranca el orquestador en ciclo continuo
├── shutdown.py                          # Shutdown — detiene gracefully vía SIGTERM/SIGKILL
├── reboot.py                            # Reboot — stop + relaunch
├── orchestrator.py                      # Orquestador maestro — ejecuta ciclos
├── config/
│   ├── sentinel_config.py               # Configuración central (secrets vía os.environ + YAML)
│   └── sentinel.yaml                    # Config declarativa (yaml, env vars override)
│
├── core/
│   ├── shared/
│   │   ├── agent_base.py                # BaseAgent, PadreAgent, SignalType, ConsensusResult
│   │   ├── data_pipeline.py             # Pipeline base para ingesta de datos
│   │   └── geometria_uvg.py             # Matriz UVG-125 Becker-Hagens estática en RAM
│   ├── precursor/
│   │   ├── risk_calculator.py           # Fórmula Fantasma TITAN V32
│   │   ├── scanner.py                   # Scanner de 15 tipos de precursor
│   │   ├── muro_cinco_eventos.py        # Motor de correlación cruzada 5 muros
│   │   ├── precursor_types.py           # Registro de tipos + funciones de detección
│   │   └── assertivity.py              # Tracking de asertividad V46
│   ├── firmas/
│   │   └── signature_engine.py          # Memoria de patrones por bot (nueva→consolidada)
│   ├── juez/
│   │   └── juez.py                      # Auditor frío separado del Padre (ACIERTO/FALLO/FP)
│   └── snt_engine/
│       ├── satellization.py             # R(t) = a*t^b — fits y regímenes
│       ├── friction.py                  # Calculador de fricción institucional
│       ├── asi.py                       # Índice de Soberanía Atómica
│       ├── nbody.py                     # Procesador N-Body multi-entidad
│       └── corpus.py                    # Corpus de observaciones empíricas (satelización)
│
├── layers/
│   └── geodynamic/                      # Los 8 agentes (SNT 5 + Omega + Loki + Padre) único
│       ├── alfa1/agent.py               # NOAA OMNI: Bz, viento solar
│       ├── alfa2/agent.py               # ESA Sentinel-2 multispectral
│       ├── beta1/agent.py               # Kp FFT + filtro Schumann
│       ├── beta2/agent.py               # Sentinel-1 SAR InSAR / química atmosférica
│       ├── delta/agent.py               # Correlación financiera + atmosférico
│       └── padre/agent.py               # Consenso asimétrico + Fantasma + Scanner + Muro
│
├── infrastructure/
│   ├── api/                             # 10 conectores + resilience
│   │   ├── _http.py                     # Session con Retry + tenacity + circuit breaker
│   │   ├── circuit_breaker.py           # Circuit breaker (CLOSED/OPEN/HALF_OPEN)
│   │   ├── noaa.py                      # NOAA SWPC (Bz, Kp, protones)
│   │   ├── usgs.py                      # USGS FDSN (catálogo sísmico)
│   │   ├── schumann.py                  # Tomsk SRF (resonancia Schumann)
│   │   ├── esa_sentinel.py              # ESA Copernicus (Sentinel-1/2)
│   │   ├── openweathermap.py            # OpenWeatherMap (atmosférico)
│   │   ├── noaa_hazards.py              # NOAA NHC (ciclones tropicales)
│   │   ├── geophysical.py               # IERS LOD
│   │   ├── crypto.py                    # CoinGecko + Binance + Bitso (Delta)
│   │   ├── bolsa.py                     # Yahoo Finance + Alpha Vantage (Delta)
│   │   └── telegram.py                  # Telegram Bot API
│   ├── pipeline/
│   │   ├── data_pipeline.py             # Pipeline maestro con LOCF
│   │   ├── layer_runners.py             # GeodynamicLayerRunner (8 agentes: SNT×5 + Omega + Loki + Padre)
│   │   ├── backcast.py                  # Carga histórica one-time (1994-2025, 1H)
│   │   └── legacy_loader.py             # Cargador de datos TITAN legacy
│   ├── database/
│   │   ├── schema.py                    # Schema SQLite + WAL + triggers + backcast + migración
│   │   ├── repository.py                # CRUD + 12 queries analíticas
│   │   └── seed_nodos.py                # 125 nodos semilla (malla global)
│   ├── dashboard/  (api.py FastAPI :8787 + web/ React 6 tabs + app.py Streamlit)
│   │   └── app.py                       # Dashboard Streamlit (11 tabs legacy, puerto 8510)
│   ├── logging/                         # Logging estructurado JSON
│   │   └── formatter.py                 # JSONFormatter + RotatingFileHandler
│   ├── health/                          # Health checks (DB/disk/APIs/pipeline)
│   │   └── checks.py                    # HealthChecker + get_health()
│   └── telegram/
│       └── bot.py                       # Bot Telegram para alertas
│
├── tests/                               # 301 tests
│   ├── test_snt_engine.py               # Tests SNT (satellization, friction, ASI, N-Body)
│   ├── test_agents.py                   # Tests de agentes (8 agentes)
│   ├── test_precursor.py                # Tests precursor (fantasma, scanner, muro, assertivity)
│   ├── test_schumann_filter.py          # Tests Schumann filter + DB schema
│   ├── test_api_connectors.py           # Tests de conectores API
│   ├── test_pipeline.py                 # Tests de pipeline + layer runners
│   └── test_infrastructure.py           # Tests de infraestructura (config, DB, telegram)
│
└── data/                                # Bases de datos SQLite
    └── SENTINEL_OMEGA_PRO.db            # DB principal (6 tablas operacionales + 6 backcast)
```

---

## Observabilidad y Resilience (v2.5.3 — 2026-08-29)

### Logging estructurado JSON
- `infrastructure/logging/formatter.py`: `JSONFormatter` + `RotatingFileHandler` (10MB x 5).
- Cada linea: `{"timestamp": "2026-08-29T02:44:00Z", "level": "INFO", "logger": "..."}`. Configurable `json`/`text` via `sentinel.yaml` (`logging.format`).

### Health checks
- `infrastructure/health/checks.py`: `HealthChecker` verifica `database` (sqlite_master), `disk` (shutil), `apis` (NOAA 200), `pipeline` (MAX(ts) en tbl_salud_sistema).
- Uso: `python -m sentinel_omega.infrastructure.health.checks` o `HealthChecker().run_all().to_dict()`.

### Resilience: Retry + Circuit Breaker
- `infrastructure/api/_http.py`: `urllib3.Retry` (429/500/502/503/504, backoff 1s->4s) + `tenacity` (`retry_api`, `fetch_with_retry`) para `ConnectionError`/`Timeout`.
- `infrastructure/api/circuit_breaker.py`: `CircuitBreaker` CLOSED->OPEN->HALF_OPEN, thread-safe, decorador `@circuit(name)` en `noaa.py`, `usgs.py`, `nasa_neo.py`.

### Config declarativa
- `config/sentinel.yaml`: defaults versionados. Env vars hacen override. `sentinel_config.load_config()` mergea YAML + env.
- `sentinel_omega/.env.example`: `LOG_LEVEL`, `LOG_FORMAT`, `CB_*` centralizados.

### Alertas enriquecidas Telegram (v2.5.3)
- `infrastructure/api/telegram.py`: `send_photo(path, caption)` y `send_document(path)` — envia PNG/PDF a Telegram con caption HTML (1000 chars, timeout 20s).
- `infrastructure/messaging/charts.py`: graficas con `matplotlib Agg` en `/tmp/sentinel_charts/` (configurable `SENTINEL_CHARTS_DIR`):
  - `fantasma_timeline(valores)` — linea Fantasma con umbrales 15/30, marca ultimo punto rojo.
  - `cimatica_bars(patrones)` — barras frecuencia por patron (verde si tiene event_class).
  - `precursores_tabla_png(filas)` — tabla precursores como imagen.
- `infrastructure/messaging/alert_service.py`: nuevos templates `cimatica_consistente()` y `reporte_resumen()`.
- `orchestrator.py`: umbral 0.7 -> 0.5 (mas cobertura), cada alerta lleva descripcion detallada + tabla de activos + cimatica top-3. Si `fantasma>5`, envia `fantasma_timeline` como foto (ultimos 10 valores de `tbl_salud_sistema`).
- `core/firmas/cimatica.py`: cuando `frecuencia==3` dispara `AlertService` (telegram+log) + `cimatica_bars` con top-5 patrones `frecuencia>=2` como foto.

---

## Instalación

```bash
pip install -e ".[all]"
```

### Dependencias Principales

```
numpy>=1.24          # Computación numérica, FFT
scipy>=1.10          # Estadística, Pearson, Mann-Whitney
pandas>=2.0          # DataFrames para análisis
requests>=2.28       # HTTP para APIs
onnxruntime>=1.14    # Inferencia ML (precursor tipo 11)
streamlit>=1.28      # Dashboard interactivo
plotly>=5.15         # Visualizaciones
pyyaml>=6.0          # Config YAML (config/sentinel.yaml)
tenacity>=8.2        # Retry con backoff exponencial + circuit breaker
python-dotenv>=1.0   # .env para secrets (no hardcode)
```

## Ejecución

```bash
# Tests (396 tests, ejecutar desde /home/user/workspaces/)
python -m pytest sentinel_omega/tests/ -q

# Dashboard (9 tabs interactivas)
streamlit run sentinel_omega/infrastructure/dashboard/app.py
```

### Launcher / Shutdown / Reboot

```bash
# Iniciar el orquestador en ciclo continuo
python sentinel_omega/launcher.py

# Iniciar con dashboard + sin alertas Telegram (dry run)
python sentinel_omega/launcher.py --dashboard --dry-run

# Un solo ciclo y salir
python sentinel_omega/launcher.py --once

# Carga histórica (one-time, 1994-2025)
python sentinel_omega/launcher.py --backcast

# Entrenamiento completo (sesgo PRE → Fase 1 sísmica → Fase 1b no sísmica →
# Fase 2 disciplina → lags → correlaciones → cimática histórica → sesgo POST)
python sentinel_omega/launcher.py --entrenar

# Disciplina de trasfondo (sismos menores M3.3-4.49, tabla temporal)
python sentinel_omega/launcher.py --disciplina

# Barrido diario (compacta historial, correlaciones, orden, sesgo, poda cimática)
python sentinel_omega/launcher.py --barrido

# Los flags de tarea (--entrenar/--disciplina/--barrido/--backcast) corren
# la tarea y SALEN; solo entran al ciclo continuo sin flags o con --once.

# Pasada del Juez: real vs predicción (ritmo auto-impuesto de 4h)
python deploy/verificacion_juez.py

# Reportes periódicos (comparativo diario / semanal / mensual, con gráficas)
python deploy/reporte_periodico.py --comparativo
python deploy/reporte_periodico.py --semanal
python deploy/reporte_periodico.py --mensual

# Despacho del outbox de correo
python deploy/enviar_correos.py

# Detener gracefully (SIGTERM -> espera 30s)
python sentinel_omega/shutdown.py

# Detener forzado (SIGKILL si no responde)
python sentinel_omega/shutdown.py --force

# Reiniciar (stop + relaunch)
python sentinel_omega/reboot.py
python sentinel_omega/reboot.py --dashboard --dry-run
```

---

## Integración Telegram Bidireccional (v2.5.3+)

Sentinel Omega se integra con **Consensus Expert Agent** vía Telegram bot compartido:

### Flujo Sentinel Omega → Usuario (Alertas)
```python
from sentinel_omega.infrastructure.api import telegram as tg
tg.send_alert("Mensaje de alerta HTML", chat_id="8056592822")
```
- Envía alertas de precursores detectados en tiempo real
- Soporta `send_photo()` y `send_document()` para gráficas PNG/PDF
- Templates enriquecidos: `centinela_advertencia()`, `cimatica_consistente()`, `reporte_resumen()`

### Flujo Usuario → Consensus Expert Agent (Comandos)
El bot `@IngZainos_bot` (corriendo en Consensus Expert Agent) recibe comandos y consulta Sentinel Omega:

| Comando | Función |
|---------|---------|
| `/start` | Menú principal con botones inline |
| `/task <prompt>` | Tarea al Concilio (Nemotron → DeepSeek → Gemma) |
| `/audit [foco]` | Auditar Sentinel (tests, secrets, migrations, automation) |
| `/status` | Estado Sentinel Omega (ciclos, precursores, Juez) — **lee BD real** |
| `/blackboard` | Ver pizarra de consenso activa |
| `/cancel` | Cancelar tarea en curso |

### Configuración compartida
Ambos sistemas usan las **mismas credenciales** en sus respectivos `.env`:
```bash
TELEGRAM_BOT_TOKEN=8016695154:AAF8JjOp6vjaljbuKF831y3o2se3Y0rKgv0
TELEGRAM_CHAT_ID=8056592822,8016695154
```

### Ejecutar bot de Consensus
```bash
cd /home/deamon/consensus-expert-agent
./run_telegram_bot.sh
# O directamente:
python telegram_bot.py
```

### Dashboard Streamlit (Sentinel Omega)
```bash
cd /home/deamon/workspaces/sentinel_omega
python -m streamlit run sentinel_omega/infrastructure/dashboard/app.py --server.port 8502 --server.address 0.0.0.0
```
**Acceso:** `http://localhost:8502` (local) | `http://192.168.1.144:8502` (red LAN)

Tabs: Precursor Risk (Fantasma) | Muro 5 Eventos | SNT Engine | Alerts & Charts | Database | Agent Tab

---

## Concilio Operativo (verificado 02/09/2026)

El bot `@IngZainos_bot` ejecuta **consenso real** Nemotron → DeepSeek → Gemma:

1. **Usuario** envía `/task` o usa botón "🚀 Nueva Tarea"
2. **Bot** muestra: `🔄 Iniciando Concilio... 🔍 Nemotron... 💻 DeepSeek... ⚖️ Gemma...`
3. **Nemotron** (investigador): Analiza, busca patrones, propone arquitectura → Blackboard
4. **DeepSeek** (coder): Lee investigación, implementa código tipado → Blackboard
5. **Gemma** (optimizador): Audita, calcula score 0-100, sintetiza → resultado
6. **Refinamiento**: Si score < 85, feedback a DeepSeek (máx 3 rondas)
7. **Entrega**: Bot edita mensaje con síntesis final + teclado principal

**Log real (07:30-07:35):**
- Usuario: "Puedes revisar la seguridad"
- 4 llamadas Ollama secuenciales (Nemotron → DeepSeek → Gemma → Síntesis)
- Respuesta final via `editMessageText` en <5 min
- `/status` lee BD real: 10,651 ciclos, 1,418 alertas, 29,270 predicciones, 897,356 eventos Juez

---

| Archivo                     | Propósito                              |
|-----------------------------|----------------------------------------|
| `data/sentinel_omega.pid`   | PID del proceso activo                 |
| `data/sentinel_omega.log`   | Log persistente del orquestador        |

El launcher:
- Verifica que no haya otra instancia corriendo (vía PID file)
- Inicializa la base de datos, aplica migraciones y siembra los 125 nodos si está vacía
- Ejecuta ciclos en loop con el intervalo configurado (default 300s)
- Maneja SIGTERM/SIGINT para shutdown graceful
- Persiste cada ciclo en SQLite (precursores cósmicos + ciclos + detecciones + muro)
- Opcionalmente lanza el dashboard de Streamlit como proceso hijo
- El flag `--backcast` ejecuta la carga histórica antes de iniciar ciclos

## Variables de Entorno

```bash
export SMTP_USER="..."                 # Cuenta emisora de correo (canal de alertas)
export SMTP_PASS="..."                 # App password de Gmail
export CORREO_DESTINO="..."            # Destinatario (default elan.zainos.corona@gmail.com)
export OPENWEATHERMAP_KEY="..."        # Datos atmosféricos (presión, humedad)
export COINGECKO_API_KEY="..."         # Datos de mercado crypto
export ALPHA_VANTAGE_KEY="..."         # Datos bursátiles
export BITSO_API_KEY="..."             # Exchange Bitso
export BITSO_API_SECRET="..."          # Exchange Bitso
export TELEGRAM_BOT_TOKEN="..."        # Telegram (en pausa: el canal es correo)
export TELEGRAM_CHAT_ID="..."          # Telegram (en pausa)
export LOG_LEVEL="INFO"                # DEBUG/INFO/WARNING/ERROR (yaml: logging.level)
export LOG_FORMAT="json"               # json/text
export CB_FAILURE_THRESHOLD="5"         # Circuit breaker: fallos para abrir
export CB_RECOVERY_TIMEOUT="60"         # Circuit breaker: segundos para HALF_OPEN
```

> **Seguridad**: Todas las claves se cargan exclusivamente vía `os.environ.get()`. Nunca se hardcodean tokens en el código. Las claves se rotan según se van usando.

---

## Linaje

| Versión  | Sistema          | Aportación                                           |
|----------|------------------|------------------------------------------------------|
| V32      | TITAN V32        | Fórmula Fantasma, Schumann WPC, 2 muros (Geo+Solar) |
| V46      | TITAN V46        | Asertividad, validación contra USGS, hits/misses     |
| V53      | TITAN V53        | Patrones WPC, Lorenz-X/Lyapunov, multi-horizonte     |
| v2.5     | Sentinel Omega   | 15 precursores, 5 muros, 125 nodos, 6 agentes, dashboard, backcast 1H |
| v2.5.2   | Sentinel Omega   | Observabilidad: logging JSON + health + circuit breaker/tenacity + YAML + ruff/mypy |
| v2.5.4   | Sentinel Omega   | The Third Act: Loki Fractal-Bayesiano + SNT Artist/Analyst + Fin stress + FastAPI compat (React 6 tabs) |
| v2.5.1   | Sentinel Omega   | Honestidad total: fase estricta + viva_real, verdad por fila con nodos propios, línea base de Molchan, agentes honestos (beta1 Schumann medido, alfa1 ONNX real, delta contexto, alfa2 proxy degradado), Omega (ritmo cósmico), cimática con retro-etiquetado y poda, correo con gráficas, rutinas 24/7 |

---

## Licencia

Proprietary — Fractal Core Research

**Autor**: Elán Zainos Corona
**Contacto**: elan.zainos.corona@gmail.com
