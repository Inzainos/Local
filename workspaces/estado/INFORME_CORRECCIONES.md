# Informe de revisión profunda — encontrado y corregido

**Fecha:** 2026-07-10 · **Rama:** `claude/sentinel-omega-architecture-j3c2kn`
**Alcance:** lista de fixes Bloques A–D + barrido completo del pipeline en busca de incongruencias.

---

## 1. Lo que se encontró (hallazgos)

### 🔴 Graves — números que mentían

| # | Hallazgo | Dónde |
|---|---|---|
| H1 | **Las 183 resoluciones "viva" estaban contaminadas**: todas compartían la misma verdad — un evento de **1994** del backcast (`1994-01-01 02:00\|nodo14\|M5.1`), aplicado en bloque el 9 de julio por una corrida de entrenamiento anterior al filtro de fase. La asertividad viva (36.6%) estaba calculada contra un fantasma de hace 32 años. | `TBL_JUEZ_AUDITORIA` |
| H2 | **El criterio vivo de verdad era el modelo nulo puntuando como habilidad**: "¿hubo algún M4.5+ en la Tierra en los últimos 4 días?" es cierto prácticamente siempre (ocurren varios al día). Con ese criterio, todo `watch` era ACIERTO automático y todo silencio FALLO automático — geografía, no predicción. | `launcher.py` + `juez.py` |
| H3 | **beta1 "coherencia armónica Schumann" era numerología**: 7.83 Hz está ~5 órdenes de magnitud sobre el Nyquist del Kp muestreado a 3 h; la coherencia salía ≈1 siempre y regalaba confianza. | `beta1/agent.py` |
| H4 | **alfa1 decía correr ML sin correrlo**: el reasoning afirmaba inferencia cuando solo aplicaba umbrales de Bz. | `alfa1/agent.py` |

### 🟡 Medias — sesgos estructurales

| # | Hallazgo | Dónde |
|---|---|---|
| H5 | **delta votaba ALERT sísmico** con datos financieros, y sumaba un `friction` inventado (constantes 0.4/0.3/0.5 hardcodeadas) al score compuesto. | `delta/agent.py` |
| H6 | **alfa2 emitía ALERT térmica sin termómetro**: el conteo de anomalías térmicas llega de fuera (el pipeline lo entrega en 0) y no hay ninguna medición LST (`lst_c`) detrás — proxy de proxy. | `alfa2/agent.py` |
| H7 | **correlación Tierra-Luna espuria** en ventanas cortas: dos series suaves dan \|r\| alto por azar. | `beta1/agent.py` |
| H8 | **La sección "El Juez" del reporte mezclaba 178,584 filas de entrenamiento** con la operación viva, presentándolas como auditoría contra USGS. | `generar_reporte.py` |
| H9 | **alfa1 asumía que la columna 0 era Bz**: si `bz_gsm` faltara en el dataframe, la regla de umbral leería viento solar como campo magnético; el vector ONNX se rellenaba con pad ciego (desalineación de features). | `alfa1/agent.py` |
| H10 | **Caída de USGS se confundía con calma**: un fetch fallido resolvía pendientes como "sin eventos" (FALSO_POSITIVO injusto). | `launcher.py` |
| H11 | **No existía línea base**: ningún número del sistema se comparaba contra lo que lograría un bot sin cerebro que alerta siempre (Molchan). | (faltante) |
| H12 | `AssertivityTracker` está instanciado en el runner pero **nunca se alimenta en operación** (nadie llama `record_prediction`/`ingest_events` fuera de tests). | `layer_runners.py` |
| H13 | La severidad por reincidencia crece sin techo dentro de un mismo lote de resolución (llegó a 1,573 en un lote de 183). No rompe nada hoy (los pesos se ajustan por otra vía), pero se documenta para vigilarlo. | `juez.py` |

---

## 2. Lo que se corrigió

| # | Corrección | Estado |
|---|---|---|
| H1 | Las 183 filas se regresaron a PENDIENTE y se **re-resolvieron contra el catálogo USGS real de julio 2026**, cada una contra su propia ventana de 72 h y los 50 nodos reales a ≤5°. Resultado: mismos agregados (67 ACIERTO / 116 FALLO, 36.6%) pero ahora con verdad real por fila. | ✅ |
| H2 | `evaluar_pendientes` acepta `eventos` (verdad **por fila**: ventana propia de 72 h + zonas monitoreadas a 5°) y el launcher lo usa con los nodos reales de la malla. | ✅ |
| H3 | beta1 reescrito: FFT del Kp como feature espectral **plana** (`kp_spectral_features`: energía, ratio de alta frecuencia, periodo dominante); el Schumann que sube confianza es el **MEDIDO** de Tomsk (excitación >15% suma, >30% con espectro calmo → WATCH). | ✅ |
| H4 | alfa1 honesto: carga ONNX fail-soft (`_try_load_onnx`), `set_model()` inyectable, `_analyze_onnx()` con fallback; el reasoning dice **qué rama corre** ("ONNX inference:…" vs "Bz threshold rule:…") y `data.onnx` lo marca. | ✅ |
| H5 | delta **nunca emite ALERT** (techo WATCH — contexto para el Padre, no voto sísmico); `friction` eliminado del score; `health_check` usa flag `_ingested` (VIX=20 exacto ya no cuenta como "sin datos"). La familia financiera sigue activando el conteo de familias vía WATCH. | ✅ |
| H6 | alfa2: limitación proxy-of-proxy documentada en el módulo; sin `lst_c` medida, el conteo térmico **degrada a WATCH** y el reasoning lo dice. ALERT térmica exige LST real. | ✅ |
| H7 | `correlacion_TL` exige ≥3 ciclos lunares completos (wraps de fase); con ventana corta reporta `None` y jamás alimenta confianza. | ✅ |
| H8 | Sección del Juez separada por fase: "Operación viva (lo que cuenta)" vs "Bitácora de entrenamiento (no puntúa)". | ✅ |
| H9 | Bz se busca **por nombre de columna**; sin `bz_gsm` el agente lo dice y queda NEUTRAL; el vector ONNX se alinea por nombre al orden canónico de features. | ✅ |
| H10 | USGS caído → resolución **pospuesta** (queda PENDIENTE para el siguiente ciclo), nunca "sin eventos" inventado. | ✅ |
| H11 | **Línea base de Molchan**: `core/precursor/baseline.py` (modelo nulo alertar-siempre, misma geometría 5°/72 h), hook `validate_with_baseline()` en assertivity, y sección "¿Le ganamos a alertar siempre?" en el reporte general con la **ganancia** (sistema ÷ tasa base). | ✅ |
| H12 | **Conectado**: el launcher ahora alimenta el `AssertivityTracker` cada ciclo (avisos anclados a sus nodos + eventos USGS) y loguea la **ganancia de Molchan en vivo** vía `validate_with_baseline()`. | ✅ |
| H13 | Documentado; sin cambio de semántica de castigo (decisión consciente: el castigo duro es de diseño). | 📋 |

Además, del fix list original: **C1** (columna `fase` real + vista `viva_real` + auditoría viva append-only + resolución filtrada por fase) y **C2** (las tres tuberías de reporte unificadas sobre `viva_real`) quedaron aplicados y verificados sobre la base real.

---

### ⚔️ El ataque al 0.37× — predicciones específicas por nodo

La razón por la que el modelo nulo gana es que un aviso global se validaba
contra **toda** la malla (50 nodos a 5° ≈ casi siempre hay un sismo cerca de
alguno). Ahora:

- El Padre registra **los nodos de las firmas que motivaron su aviso**
  (`nodos` en detalles) — el aviso dice *dónde*.
- El Juez valida cada fila **solo contra sus propios nodos**: acertar es
  acertar donde avisaste; un sismo en Japón ya no valida un aviso en
  Guerrero. Los silencios (`no_signal`) se siguen juzgando contra toda la
  malla — callar sí se mide contra todo lo monitoreado.
- Con la vara espacial estrecha, la tasa base por aviso baja de ~100% a la
  sismicidad real del nodo señalado — ahí sí se puede (y se debe) ganar >1×.

## 3. El número honesto de hoy

- **Tasa base (alertar siempre): 100%** de las ventanas evaluadas tuvieron un M4.5+ cerca de la malla.
- **Asertividad del sistema: 36.6%** → **ganancia 0.37×** → 🔴 SIN ganancia: alertar a ciegas habría rendido mejor.
- Conclusión operativa: con 50 nodos reales y radio de 5°, casi toda ventana de 72 h tiene un sismo "cerca de algún nodo". Para ganar de verdad, las predicciones tendrán que volverse **específicas por nodo**, no globales. Ese es el siguiente escalón del proyecto, y ahora el reporte lo mide en cada corte.

## 3.5 Cambios posteriores al informe (mismo PR)

- **Sistema 24/7** (Roy Vigilante): Padre cada 2 h · Juez cada 4 h (ritmo
  auto-impuesto) · ejecutivo cada 6 h · comparativo 12am/12pm MX · semanal
  domingo 12:15pm · mensual fin de mes 12:30pm · correo cada corrida.
  De paso: el gate viejo de disciplina (07 UTC) nunca disparaba (cron en
  horas pares) — corregido.
- **Cimática** (`tbl_cimatica_patrones`): snapshot de telemetría por ciclo
  (nuevo = telemetría completa; repetido = frecuencia+1), entrenada también
  desde el histórico de 30 años (`entrenar_cimatica`), **retro-etiquetada**
  por los eventos reales que confirma el Juez y **podada** por ruido (30 días
  de gracia sin evento asociado). Trigger del Padre en cada alta/incremento.
- **Correo sin Telegram** (`tbl_correo_salida` + SMTP fail-soft): alertas
  cimáticas y reportes con gráficas a elan.zainos.corona@gmail.com.
- **Piso de medición en 3.3** (alineado al piso real del backcast, M3.38):
  se mide y predice desde M3.3 con su clase de desastre; alerta solo ≥4.5.
- Confirmado: el Juez disciplina en el ENTRENAMIENTO y el POST; el PRE mide
  sin castigo (línea base pura).

## 4. Verificación

- Suite completa: **371 tests en verde** (nuevos: 4 de verdad-por-fila del Juez, 9 de línea base Molchan, 2 de degradación proxy en alfa2, reescritura de 14 tests de beta1).
- Reportes regenerados contra la base real: sección Molchan y Juez-por-fase renderizan correctamente.
- **Reentrenamiento limpio total** de memorias (firmas, pesos, correlaciones, orden, sesgo, lags) ejecutado tras las correcciones para eliminar sesgos de versiones anteriores; la fase viva (append-only) y los datos crudos del backcast se conservan.
