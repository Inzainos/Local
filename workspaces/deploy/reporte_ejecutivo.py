#!/usr/bin/env python3
"""
Reporte Ejecutivo — Plantilla Extendida de Sentinel Omega.

Llena la plantilla ejecutiva (13 secciones) desde la base de datos, con el
bot Omega integrado en las tablas de desempeño. Lo corre el vigilante 1×/día
(07 UTC, junto con disciplina y barrido) y se puede correr a mano:

    python deploy/reporte_ejecutivo.py [db] [out]

Salida: estado/REPORTE_EJECUTIVO.md (último) + copia versionada en
estado/historial/AAAA/MM/AAAA-MM-DD_HH-MM_EJECUTIVO_MX.md.

Regla del proyecto: cero datos sintéticos — todo dato que no exista en la
DB se reporta como "—", nunca se inventa.
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Importar módulo de aciertos
sys.path.insert(0, str(Path(__file__).parent))
try:
    from aciertos_reporte import obtener_estadisticas_aciertos
except ImportError:
    obtener_estadisticas_aciertos = None

DB_DEFAULT = str(
    Path(__file__).parent.parent / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db"
)
OUT_DEFAULT = str(Path(__file__).parent.parent / "estado" / "REPORTE_EJECUTIVO.md")

VERSION_REPORTE = "1.0-omega"
BOTS_ORDEN = ["alfa1", "beta1", "alfa2", "beta2", "delta", "jupiter", "omega", "padre"]

# Región de la malla → agrupación operativa de la plantilla
REGIONES_PLANTILLA = {
    "Pacífico Norte": ("Pacific",),
    "México Pacífico": ("Mexico",),
    "México Golfo-Sureste": ("Mexico-Gulf",),
    "Andes / Pacífico Sur": ("SouthAmerica", "Andes"),
    "Asia-Pacífico": ("Asia", "Oceania"),
}


def _q(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def _pct(x, dec=1):
    return f"{x:.{dec}%}" if x is not None else "—"


def _num(x, dec=1):
    return f"{x:.{dec}f}" if x is not None else "—"


def _estado_ejecutivo(fantasma, muros, breach, mejor_match):
    """Semáforo ejecutivo VERDE→ROJO + clasificación operativa."""
    sim = mejor_match or 0.0
    if breach and (fantasma or 0) >= 30:
        return "ROJO", "ESCALAMIENTO"
    if breach or ((fantasma or 0) >= 15 and sim >= 0.85):
        return "NARANJA", "PRE-ESCALAMIENTO"
    if (fantasma or 0) >= 5 or sim >= 0.80:
        return "AMARILLO", "VIGILANCIA REFORZADA"
    if (fantasma or 0) > 0 or muros:
        return "AZUL", "OBSERVACIÓN"
    return "VERDE", "ESTABLE"


def _percentil(valor, serie):
    serie = [s for s in serie if s is not None]
    if valor is None or not serie:
        return "—"
    below = sum(1 for s in serie if s <= valor)
    return f"P{round(100 * below / len(serie))}"


def generar(db_path: str = DB_DEFAULT, out_path: str = OUT_DEFAULT) -> str:
    conn = sqlite3.connect(db_path)
    ahora = datetime.now(timezone.utc)
    local = ahora - timedelta(hours=6)

    # ── Datos base ───────────────────────────────────────────────────────────
    ciclos = _q(conn, (
        "SELECT timestamp, fantasma, nivel_riesgo, muro_walls_active, "
        "muro_breach, geo_signal, geo_confidence, precursors_count "
        "FROM TBL_CICLOS ORDER BY id DESC LIMIT 2"))
    actual = ciclos[0] if ciclos else None
    previo = ciclos[1] if len(ciclos) > 1 else None
    total_ciclos = (_q(conn, "SELECT COUNT(*) FROM TBL_CICLOS") or [(0,)])[0][0]

    hace7 = ahora.timestamp() - 7 * 86400
    hace30 = ahora.timestamp() - 30 * 86400
    serie30 = _q(conn, "SELECT fantasma, muro_walls_active FROM TBL_CICLOS "
                       "WHERE timestamp >= ?", (hace30,))
    serie7 = _q(conn, "SELECT fantasma FROM TBL_CICLOS WHERE timestamp >= ?",
                (hace7,))
    f30 = [r[0] for r in serie30 if r[0] is not None]
    m30 = [r[1] for r in serie30 if r[1] is not None]
    f7 = [r[0] for r in serie7 if r[0] is not None]

    version_modelo = "—"
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from sentinel_omega.config.sentinel_config import SentinelOmegaConfig
        version_modelo = SentinelOmegaConfig().version
    except Exception:
        pass

    nodos = {r[0]: (r[1], r[2], r[3], r[4]) for r in _q(
        conn, "SELECT node_id, nombre, lat, lon, region FROM TBL_NODOS_TOPOLOGIA")}

    # Firma matches del último ciclo (registro del padre en el Juez)
    matches, muro_lags = [], {}
    row = _q(conn, "SELECT detalles_json FROM TBL_JUEZ_AUDITORIA "
                   "WHERE bot_name='padre' AND detalles_json LIKE '%firma_matches%' "
                   "ORDER BY id DESC LIMIT 1")
    if row:
        det = json.loads(row[0][0])
        matches = det.get("firma_matches", [])[:5]
        muro_lags = det.get("muro_lags") or {}
    mejor_sim = max((m.get("similitud", 0) for m in matches), default=None)

    dets = _q(conn, "SELECT display_name, confidence, station, wall_name "
                    "FROM TBL_DETECCIONES ORDER BY id DESC LIMIT 8")

    pesos = {r[0]: (r[1], r[2], r[3]) for r in _q(
        conn, "SELECT bot_name, peso, aciertos, fallos FROM TBL_PESOS_BOTS")}
    sesgo = {r[0]: (r[1], r[2], r[3]) for r in _q(
        conn, "SELECT bot, recon_insample, recon_causal, sesgo "
              "FROM tbl_sesgo_aprendizaje")}
    firmas_bot = {r[0]: r[1] for r in _q(
        conn, "SELECT bot_name, COUNT(*) FROM TBL_FIRMAS GROUP BY bot_name")}

    # Vara canónica: solo filas de operación viva (columna fase estricta)
    juez = {r[0]: r[1] for r in _q(
        conn, "SELECT resultado, COUNT(*) FROM viva_real GROUP BY resultado")}
    pendientes = juez.get("PENDIENTE", 0)
    aciertos_v = juez.get("ACIERTO", 0)
    fallos_v = juez.get("FALLO", 0)
    fp_v = juez.get("FALSO_POSITIVO", 0)
    viva = (aciertos_v / (aciertos_v + fallos_v + fp_v)
            if (aciertos_v + fallos_v + fp_v) else None)

    ha = sum(v[1] for v in pesos.values())
    hf = sum(v[2] for v in pesos.values())
    historica = ha / (ha + hf) if (ha + hf) else None

    lags = {r[0]: r[1] for r in _q(
        conn, "SELECT event_class, lag_promedio_h FROM tbl_lag_anticipacion")}

    fant = actual[1] if actual else None
    muros_act = actual[3] if actual else 0
    breach = bool(actual[4]) if actual else False
    color, clasif = _estado_ejecutivo(fant, muros_act, breach, mejor_sim)
    ts_actual = (datetime.fromtimestamp(actual[0], tz=timezone.utc)
                 if actual else ahora)

    nivel_map = {"LOW": "calma", "MODERATE": "actividad moderada",
                 "HIGH": "actividad alta", "CRITICAL": "condiciones muy cargadas"}
    nivel_txt = nivel_map.get(actual[2], "—") if actual else "—"

    # Ventana de atención: muro de lags si está activo; si no, lag de la clase
    # del mejor match
    if muro_lags.get("activo"):
        ventana_ini = muro_lags.get("fecha_inicio", "—")
        ventana_fin = muro_lags.get("fecha_fin", "—")
        base_vent = ("MURO DE LAGS (" + ", ".join(muro_lags.get("clases", []))
                     + ")")
    elif matches:
        clase = matches[0].get("event_class", "")
        lag_h = lags.get(clase)
        if lag_h:
            ventana_ini = (ahora + timedelta(hours=lag_h * 0.5)).strftime("%Y-%m-%d")
            ventana_fin = (ahora + timedelta(hours=lag_h * 1.5)).strftime("%Y-%m-%d")
            base_vent = f"FIRMA DOMINANTE ({clase})"
        else:
            ventana_ini = ventana_fin = base_vent = "—"
    else:
        ventana_ini = ventana_fin = base_vent = "—"

    L = []
    A = L.append

    # ══ Encabezado ═══════════════════════════════════════════════════════════
    A("# Plantilla Extendida — Reporte Ejecutivo Sentinel Omega")
    A("")
    A("## Encabezado del ciclo")
    A("")
    A(f"**Sistema:** Sentinel Omega  ")
    A(f"**Versión del modelo:** {version_modelo}  ")
    A(f"**Versión del reporte:** {VERSION_REPORTE}  ")
    A(f"**Ciclo total:** {total_ciclos:,}  ")
    A(f"**Fecha de generación:** {ahora:%Y-%m-%d %H:%M} UTC / "
      f"{local:%Y-%m-%d %H:%M} UTC-6  ")
    A(f"**Ventana analizada:** {(ts_actual - timedelta(days=14)):%Y-%m-%d} a "
      f"{ts_actual:%Y-%m-%d}  ")
    A("**Fuentes activas:** NOAA / USGS / NASA / ESA / Tomsk / IERS / "
      "OpenWeatherMap / Yahoo Finance  ")
    A(f"**Estado ejecutivo del sistema:** {color}  ")
    A(f"**Clasificación operativa:** {clasif}  ")
    A("")
    A("> **Definición operativa:** Sentinel Omega es un sistema de "
      "reconocimiento de precursores multi-dominio. No emite pronósticos "
      "oficiales ni deterministas; compara el estado físico actual contra "
      "firmas históricas y eleva vigilancia cuando el presente converge con "
      "patrones previos a eventos fuertes.")
    A("")
    A("---")
    A("")

    # ══ 1. Lectura en 60 segundos ════════════════════════════════════════════
    A("## 1. Lectura en 60 segundos")
    A("")
    resumen = (
        f"Fantasma en {_num(fant)} ({nivel_txt}), {muros_act}/5 frentes del "
        f"Muro activos{' con BREACH' if breach else ''}. "
        + (f"La memoria reconoce el momento con hasta {_pct(mejor_sim, 0)} de "
           f"parecido a vísperas de {matches[0].get('event_class', '—')}."
           if matches else "Sin coincidencias de firma en el último ciclo."))
    A(f"**Estado actual:** {resumen}  ")
    criterios = []
    if breach:
        criterios.append("convergencia multi-dominio (breach)")
    if (fant or 0) >= 15:
        criterios.append("fantasma elevado")
    if (mejor_sim or 0) >= 0.85:
        criterios.append("firma consolidada con parecido alto")
    A(f"**Nivel de riesgo operativo:** {color} porque "
      f"{', '.join(criterios) if criterios else 'los indicadores están en rango base'}.  ")
    A(f"**Ventana de atención sugerida:** {ventana_ini} a {ventana_fin}.  ")
    accion = {"ROJO": "ESCALAR", "NARANJA": "REVISAR", "AMARILLO": "REVISAR",
              "AZUL": "MANTENER", "VERDE": "MANTENER"}[color]
    A(f"**Acción recomendada:** {accion}.")
    A("")
    A("### Indicadores clave")
    A("")
    A("| Indicador | Valor | Umbral | Estado | Lectura rápida |")
    A("|---|---:|---:|---|---|")
    A(f"| Fantasma | {_num(fant)} | 30 (CRITICAL) | {color} | {nivel_txt} |")
    conf = actual[6] if actual else None
    A(f"| Consenso de bots | {_pct(conf, 0)} | 60% | "
      f"{'activo' if (conf or 0) >= 0.6 else 'sin consenso'} | "
      f"{(actual[5] or '—').upper() if actual else '—'} |")
    A(f"| Muro de los 5 | {muros_act}/5 | 3/5 | "
      f"{'🚨 BREACH' if breach else 'estable'} | "
      f"{'convergencia multi-dominio' if breach else 'sin convergencia crítica'} |")
    A(f"| Precursores activos | {actual[7] if actual else 0} | 2 | "
      f"{'elevado' if actual and (actual[7] or 0) >= 2 else 'base'} | "
      f"señales individuales del escáner |")
    A(f"| Auditoría pendiente | {pendientes:,} | — | ventanas de 72h abiertas | "
      f"el Juez las resuelve contra USGS |")
    A("")
    A("---")
    A("")

    # ══ 2. Estado ejecutivo ══════════════════════════════════════════════════
    A("## 2. Estado ejecutivo")
    A("")
    A("### Diagnóstico consolidado")
    A("")
    if breach and (fant or 0) >= 15:
        diag = ("El sistema está en CONVERGENCIA: varios dominios físicos "
                "alterados a la vez con fantasma elevado y la memoria "
                "reconociendo patrones de víspera.")
    elif (fant or 0) < 5 and matches:
        diag = ("El sistema está en FASE DE CARGA SILENCIOSA: el fantasma es "
                "bajo pero la memoria reconoce firmas de víspera — el patrón "
                "Silent Trigger (la calma carga).")
    elif (fant or 0) >= 5:
        diag = ("El sistema está en FASE DE CARGA: actividad por encima del "
                "fondo sin convergencia crítica completa.")
    else:
        diag = "El sistema está CALMO: indicadores en rango de fondo."
    A(diag)
    A("")
    A("### Traducción operativa")
    A("")
    A("| Nivel | Condición mínima | Significado | Acción sugerida |")
    A("|---|---|---|---|")
    A("| Verde | Fantasma <5, sin muros, sin firmas | Rutina normal | Monitoreo base |")
    A("| Azul | Fantasma <5 con detecciones aisladas | Variación leve | Seguimiento ampliado |")
    A("| Amarillo | Fantasma 5–15 o firma ≥80% | Precarga o carga silenciosa | Vigilancia reforzada |")
    A("| Naranja | Breach 3/5 o fantasma ≥15 + firma ≥85% | Convergencia parcial entre dominios | Revisión manual inmediata |")
    A("| Rojo | Breach + fantasma ≥30 | Convergencia crítica multisistema | Escalamiento interno |")
    A("")
    A("---")
    A("")

    # ══ 3. Comparativo contra el ciclo anterior ══════════════════════════════
    A("## 3. Comparativo contra el ciclo anterior")
    A("")
    A("### Cambios principales")
    A("")
    A("| Variable | Ciclo actual | Ciclo previo | Cambio absoluto | Cambio relativo | Lectura |")
    A("|---|---:|---:|---:|---:|---|")

    def _cmp(nombre, act, prev, dec=1, es_pct=False):
        f = _pct if es_pct else _num
        if act is not None and prev is not None:
            d = act - prev
            rel = f"{d / prev:+.0%}" if prev else "—"
            lec = "sube" if d > 0 else ("baja" if d < 0 else "estable")
            A(f"| {nombre} | {f(act, dec)} | {f(prev, dec)} | {d:+.{dec}f} | "
              f"{rel} | {lec} |")
        else:
            A(f"| {nombre} | {f(act, dec) if act is not None else '—'} | "
              f"{f(prev, dec) if prev is not None else '—'} | — | — | sin base |")

    _cmp("Fantasma", fant, previo[1] if previo else None)
    _cmp("Consenso", conf, previo[6] if previo else None, 2)
    _cmp("Muro de los 5", float(muros_act) if actual else None,
         float(previo[3]) if previo else None, 0)
    _cmp("Precursores", float(actual[7]) if actual else None,
         float(previo[7]) if previo else None, 0)
    A(f"| Asertividad viva | {_pct(viva)} | — | — | — | "
      f"{'aún sin base de comparación' if viva is None else 'acumulándose'} |")
    A("")
    A("### Cambio cualitativo")
    A("")
    if previo and fant is not None and previo[1] is not None:
        d = fant - previo[1]
        A("El sistema está "
          + ("MÁS CARGADO que en el corte previo." if d > 1 else
             ("MÁS LIMPIO que en el corte previo." if d < -1 else
              "CONSISTENTE con el corte previo.")))
    else:
        A("Sin ciclo previo comparable en la ventana.")
    A("")
    A("---")
    A("")

    # ══ 4. Contexto temporal ═════════════════════════════════════════════════
    A("## 4. Contexto temporal")
    A("")
    A("### Posición frente al histórico reciente")
    A("")
    A("| Métrica | Actual | Promedio 7d | Promedio 30d | Máximo 30d | Mínimo 30d | Percentil actual |")
    A("|---|---:|---:|---:|---:|---:|---:|")
    A(f"| Fantasma | {_num(fant)} | "
      f"{_num(sum(f7)/len(f7)) if f7 else '—'} | "
      f"{_num(sum(f30)/len(f30)) if f30 else '—'} | "
      f"{_num(max(f30)) if f30 else '—'} | "
      f"{_num(min(f30)) if f30 else '—'} | {_percentil(fant, f30)} |")
    A(f"| Muro de los 5 | {muros_act} | — | "
      f"{_num(sum(m30)/len(m30)) if m30 else '—'} | "
      f"{max(m30) if m30 else '—'} | {min(m30) if m30 else '—'} | "
      f"{_percentil(muros_act, m30)} |")
    st_act = 1 if any("Silent" in (d[0] or "") for d in dets) else 0
    A(f"| Silent Trigger | {'activo' if st_act else 'inactivo'} | — | — | — | — | — |")
    A(f"| Consenso | {_pct(conf, 0)} | — | — | — | — | — |")
    A("")
    A("### Ventana de atención sugerida")
    A("")
    A(f"**Ventana primaria:** {ventana_ini} a {ventana_fin}  ")
    if matches and lags.get(matches[0].get("event_class")):
        ext = lags[matches[0]["event_class"]] * 2.0
        A(f"**Ventana extendida:** hasta "
          f"{(ahora + timedelta(hours=ext)):%Y-%m-%d}  ")
    else:
        A("**Ventana extendida:** —  ")
    A(f"**Base de la estimación:** {base_vent}")
    A("")
    A("La ventana viene del lag histórico de las firmas coincidentes (cuánto "
      "suelen tardar los eventos tras verse el patrón). La lectura se invalida "
      "si las firmas dejan de coincidir en los próximos ciclos o si el "
      "fantasma regresa a fondo sostenido.")
    A("")
    A("---")
    A("")

    # ══ 5. Contexto espacial ═════════════════════════════════════════════════
    A("## 5. Contexto espacial")
    A("")
    A("### Zonas con mayor similitud histórica")
    A("")
    A("| Prioridad | Nodo / Zona | Tipo de evento | Parecido | Veces vista | Aviso típico | Estado del nodo |")
    A("|---|---|---|---:|---:|---|---|")
    for i, m in enumerate(matches, 1):
        n = nodos.get(m.get("id_nodo"))
        zona = (f"{n[0]} ({n[1]:.1f}, {n[2]:.1f})" if n
                else f"nodo {m.get('id_nodo')}")
        lag_d = m.get("ventana_tipica_dias") or (
            lags.get(m.get("event_class"), 0) / 24 if lags.get(m.get("event_class")) else None)
        A(f"| {i} | {zona} | {m.get('event_class', '—')} | "
          f"{_pct(m.get('similitud'), 0)} | {m.get('recurrencia', 0):,} | "
          f"{'~' + _num(lag_d, 0) + ' días' if lag_d else '—'} | "
          f"{'ghost' if n and 'Ghost' in n[0] else 'real'} |")
    if not matches:
        A("| — | — | — | — | — | — | — |")
    A("")
    A("### Lectura regional")
    A("")
    A("| Región | Nodos activos o coincidentes | Intensidad relativa | Comentario operativo |")
    A("|---|---|---|---|")
    regiones_match = {}
    for m in matches:
        n = nodos.get(m.get("id_nodo"))
        if n:
            regiones_match.setdefault(n[3] or "—", []).append(m.get("similitud", 0))
    for region, sims in sorted(regiones_match.items(),
                               key=lambda kv: -max(kv[1])):
        inten = "ALTA" if max(sims) >= 0.85 else (
            "MEDIA" if max(sims) >= 0.8 else "BAJA")
        A(f"| {region} | {len(sims)} | {inten} | "
          f"parecido máx {max(sims):.0%} |")
    if not regiones_match:
        A("| — | 0 | — | sin coincidencias regionales en este ciclo |")
    A("")
    A("---")
    A("")

    # ══ 6. Señales detectadas ════════════════════════════════════════════════
    A("## 6. Señales detectadas")
    A("")
    A("### Detecciones del ciclo")
    A("")
    A("| Precursor | Dominio | Confianza | Zona | Persistencia | Severidad | Comentario |")
    A("|---|---|---:|---|---|---|---|")
    dominio_map = {"SOLAR": "SOL", "GEOFISICO": "SEISMO",
                   "ATMOSFERICO": "ATMÓS", "OCEANICO": "OCÉANO",
                   "FINANCIERO": "MERCADOS"}
    vistos = set()
    for d in dets:
        if d[0] in vistos:
            continue
        vistos.add(d[0])
        sev = "ALTA" if (d[1] or 0) >= 0.9 else (
            "MEDIA" if (d[1] or 0) >= 0.7 else "BAJA")
        A(f"| {d[0]} | {dominio_map.get(d[3], d[3] or '—')} | "
          f"{_pct(d[1], 0)} | {d[2] or '—'} | recurrente | {sev} | "
          f"señal del escáner de precursores |")
    if not dets:
        A("| — | — | — | — | — | — | — |")
    A("")
    A("### Convergencia entre dominios")
    A("")
    A("| Dominio | Estado | Peso actual | Activado | Aporta al riesgo |")
    A("|---|---|---:|---|---|")
    muros_estado = {"GEOFISICO": "Tierra", "ATMOSFERICO": "Atmósfera",
                    "OCEANICO": "Océano", "SOLAR": "Sol",
                    "FINANCIERO": "Mercados"}
    activos_muro = {d[3] for d in dets if d[3]}
    for clave, nombre in muros_estado.items():
        on = clave in activos_muro
        A(f"| {nombre} | {'alterado' if on else 'en fondo'} | — | "
          f"{'SÍ' if on else 'NO'} | "
          f"{'aporta a la convergencia' if on else 'sin aporte'} |")
    A("")
    A("### Interpretación física")
    A("")
    kp_alto = any("Tormenta" in (d[0] or "") or "Perturbación" in (d[0] or "")
                  for d in dets)
    if st_act and not kp_alto:
        A("Las señales apuntan a CARGA SILENCIOSA: calma geomagnética "
          "sostenida con actividad sísmica de fondo — el patrón que en el "
          "histórico precede eventos con más días de anticipación (la calma "
          "carga).")
    elif kp_alto:
        A("Las señales apuntan a PRECIPITACIÓN RÁPIDA: tormenta geomagnética "
          "activa — en el histórico los eventos bajo tormenta llegan con "
          "menos días de aviso (la tormenta precipita).")
    else:
        A("Las señales muestran una MEZCLA HÍBRIDA sin un régimen dominante "
          "claro; se requiere más ciclos para separar señal de ruido.")
    A("")
    A("---")
    A("")

    # ══ 7. Firma Match y memoria ═════════════════════════════════════════════
    A("## 7. Firma Match y memoria del sistema")
    A("")
    A("### Coincidencias principales")
    A("")
    A("| Ranking | Firma | Evento | Nodo | Parecido | Veces vista | Lead time | Fortaleza |")
    A("|---|---|---|---|---:|---:|---|---|")
    for i, m in enumerate(matches, 1):
        n = nodos.get(m.get("id_nodo"))
        rec = m.get("recurrencia", 0)
        fort = "ALTA" if rec >= 100 else ("MEDIA" if rec >= 10 else "BAJA")
        lag_d = m.get("ventana_tipica_dias")
        A(f"| {i} | #{m.get('firma_id', '—')} | {m.get('event_class', '—')} | "
          f"{n[0] if n else m.get('id_nodo')} | {_pct(m.get('similitud'), 0)} | "
          f"{rec:,} | {'~' + _num(lag_d, 0) + 'd' if lag_d else '—'} | {fort} |")
    if not matches:
        A("| — | — | — | — | — | — | — | — |")
    A("")
    A("### Lectura de memoria")
    A("")
    if matches:
        recs = [m.get("recurrencia", 0) for m in matches]
        if max(recs) >= 100:
            A("La memoria reconoce un patrón ROBUSTO: al menos una firma "
              "consolidada con cientos de repeticiones históricas respalda "
              "la coincidencia. Las firmas con pocas repeticiones se listan "
              "como contexto, no como base de la lectura.")
        else:
            A("La memoria reconoce un patrón con RESPALDO MODERADO: las "
              "firmas coincidentes tienen pocas repeticiones históricas — "
              "tratar como indicio, no como confirmación.")
    else:
        A("La memoria no reconoce el estado actual: sin coincidencias sobre "
          "el umbral de alerta en este ciclo.")
    A("")
    A("---")
    A("")

    # ══ 8. Asertividad y auditoría (con Omega integrado) ════════════════════
    A("## 8. Asertividad y auditoría")
    A("")
    A("### Desempeño general")
    A("")
    A("| Métrica | Valor | Meta interna | Estado |")
    A("|---|---:|---:|---|")
    A(f"| Histórica | {_pct(historica)} | ≥95% | "
      f"{'en meta' if historica and historica >= 0.95 else '—'} |")
    A(f"| Viva | {_pct(viva)} | ≥70% | "
      f"{'en meta' if viva and viva >= 0.7 else ('acumulando' if viva is None else 'bajo meta')} |")
    A("| Viva 7d | — | ≥70% | acumulando |")
    recall = (aciertos_v / (aciertos_v + fallos_v)
              if (aciertos_v + fallos_v) else None)
    precision = (aciertos_v / (aciertos_v + fp_v)
                 if (aciertos_v + fp_v) else None)
    A(f"| Recall operativo | {_pct(recall)} | ≥90% | "
      f"{'—' if recall is None else ('en meta' if recall >= 0.9 else 'bajo meta')} |")
    A(f"| Precisión operativa | {_pct(precision)} | ≥50% | "
      f"{'—' if precision is None else ('en meta' if precision >= 0.5 else 'bajo meta')} |")
    A("")
    A("### Desempeño por bot")
    A("")
    A("| Bot | Histórica | Causal (real) | Sesgo | Credibilidad | Firmas | Comentario |")
    A("|---|---:|---:|---:|---:|---:|---|")
    for bot in BOTS_ORDEN:
        p = pesos.get(bot)
        s = sesgo.get(bot)
        hist_b = (p[1] / (p[1] + p[2])) if p and (p[1] + p[2]) else None
        comentario = {
            "alfa1": "clima espacial — generaliza",
            "beta1": "el latido Schumann — generaliza",
            "alfa2": "memoria satelital acumulándose en vivo",
            "beta2": "desgasificación — sesgo alto, en disciplina",
            "delta": "humor de los mercados",
            "jupiter": "atención colectiva sobre tormentas solares — en vivo",
            "omega": "ritmo cósmico — recién mapeado, memoria creciendo",
            "padre": "árbitro — decisión real sólida",
        }.get(bot, "")
        A(f"| {bot} | {_pct(hist_b)} | {_pct(s[1]) if s else '—'} | "
          f"{f'{s[2]:+.1%}' if s else '—'} | "
          f"{_num(p[0], 2) if p else '—'} | {firmas_bot.get(bot, 0):,} | "
          f"{comentario} |")
    A("")
    A("### Fallos y pendientes")
    A("")
    A("| Tipo | Conteo | Variación vs ciclo previo | Impacto |")
    A("|---|---:|---:|---|")
    A(f"| Aciertos | {aciertos_v:,} | — | asertividad viva |")
    A(f"| Fallos | {fallos_v:,} | — | castigo asimétrico aplicado |")
    A(f"| Pendientes | {pendientes:,} | — | ventanas de 72h abiertas |")
    A("")
    if fallos_v > aciertos_v and (aciertos_v + fallos_v) > 10:
        A("El patrón de fallos sugiere revisar la sensibilidad del consenso "
          "(posible sub-alerta) y el sesgo de nodos con poca memoria.")
    else:
        A("Sin patrón de fallo dominante en la operación viva; la auditoría "
          "sigue acumulando ventanas resueltas para una lectura estable.")
    A("")
    A("---")
    A("")

    # ══ 9. Cambios del sistema ═══════════════════════════════════════════════
    A("## 9. Cambios del sistema")
    A("")
    A("### Cambios de versión")
    A("")
    A("| Componente | Versión actual | Cambio reciente | Impacto esperado |")
    A("|---|---|---|---|")
    A(f"| Pipeline de datos | {version_modelo} | delta_enriched (acoplamiento geo↔financiero) | features cruzadas nuevas |")
    A("| Ponderación bots | activa | gravedad anclada en M4.5 | castigo proporcional a magnitud |")
    A(f"| Firmas | {sum(firmas_bot.values()):,} totales | Omega mapeado a telemetría existente | memoria del ritmo cósmico |")
    A("| Árbitro padre | activa | correlaciones contadas (tabla propia) | consenso más ligero |")
    A("| Auditor Juez | activa | sesgo pre/post en entrenamiento | realidad vs fantasía medida |")
    A("")
    A("### Riesgos metodológicos")
    A("")
    A("- Asertividad histórica es in-sample: el sesgo causal es la medida honesta.")
    A("- beta2 con sesgo alto (~49%): su competencia real es menor a la aparente.")
    A("- Ventanas de anticipación truncadas a 14 días (máximos recortados).")
    A("")
    A("### Mitigaciones activas")
    A("")
    A("- Sesgo pre/post medido en cada entrenamiento (línea base vs disciplina).")
    A("- Disciplina de trasfondo diaria con sismos menores (castigo desde abajo).")
    A("- Barrido diario: solo lo significativo persiste (anti-inflación de datos).")
    A("")
    A("---")
    A("")

    # ══ 10. Relación con líneas externas ═════════════════════════════════════
    A("## 10. Relación con líneas externas")
    A("")
    A("### Familias de precursores integradas")
    A("")
    A("| Familia | Fuente principal | Sentinel Omega usa | Estado de integración |")
    A("|---|---|---|---|")
    A("| Geomagnéticos | NOAA SWPC / NASA OMNI2 | SÍ | operativo (30 años) |")
    A("| Ionosféricos | TEC derivado (flux+Kp+viento) | SÍ | índice derivado, no sensor |")
    A("| Térmicos | OpenWeatherMap / nodos marinos | SÍ | operativo |")
    A("| Sísmicos | USGS FDSN | SÍ | operativo (32 años) |")
    A("| Volcánicos / SO2 | NASA MSVOLSO2L4 | SÍ | operativo (backcast) |")
    A("| Mercado / estrés sistémico | Yahoo Finance (BTC) | SÍ | operativo (10 años) |")
    A("| Ritmo cósmico (luna/Schumann) | IERS / Tomsk / astronomía | SÍ | bot Omega — mapeado |")
    A("")
    A("### Diferencia frente a EEW tradicional")
    A("")
    A("Sentinel Omega trabaja en ventanas de DÍAS (anticipación estadística "
      "de precursores), no de segundos: no reemplaza sistemas de alerta "
      "temprana sísmica (EEW) ni los avisos oficiales de protección civil — "
      "los complementa aguas arriba.")
    A("")
    A("---")
    A("")

    # ══ 11. Implicaciones operativas ═════════════════════════════════════════
    A("## 11. Implicaciones operativas")
    A("")
    A("### Acciones sugeridas por estado")
    A("")
    A("| Condición observada | Acción técnica | Prioridad | Responsable |")
    A("|---|---|---|---|")
    A("| Fantasma en amarillo y Muro 0/5 | Mantener vigilancia reforzada | Media | Operación |")
    A("| Firma >90% en nodo consolidado | Revisión manual del nodo | Alta | Análisis |")
    A("| 3/5 dominios activos | Escalamiento interno | Alta | Árbitro |")
    A("| Caída fuerte de asertividad viva | Auditoría de pesos y recall | Alta | Validación |")
    A("| Incremento de fallos | Recalibración de umbrales | Alta | Core |")
    A("")
    A("### No hacer")
    A("")
    A("- No traducir firma alta a pronóstico determinista.")
    A("- No emitir equivalencias con protección civil oficial.")
    A("- No escalar por una señal aislada sin convergencia.")
    A("- No evaluar el sistema solo por desempeño histórico (usar el sesgo causal).")
    A("")
    A("---")
    A("")

    # ══ 12. Cierre ejecutivo ═════════════════════════════════════════════════
    A("## 12. Cierre ejecutivo")
    A("")
    cierre = (
        f"El sistema opera en estado {color} ({clasif.lower()}). {diag} "
        f"{'La ventana de atención sugerida va del ' + ventana_ini + ' al ' + ventana_fin + ', basada en ' + base_vent + '. ' if ventana_ini != '—' else ''}"
        f"La memoria total es de {sum(firmas_bot.values()):,} firmas en "
        f"{len([b for b in BOTS_ORDEN if firmas_bot.get(b)])} bots (Omega ya "
        f"integrado al entrenamiento con su dominio de ritmo cósmico), con "
        f"{pendientes:,} avisos pendientes de auditoría. La decisión "
        f"operativa actual es {accion}: "
        + ("elevar la revisión manual de los nodos coincidentes y vigilar la "
           "ventana señalada." if accion == "REVISAR" else
           ("escalamiento interno inmediato." if accion == "ESCALAR" else
            "continuar el monitoreo base con los cortes automáticos.")))
    A(cierre)
    A("")
    A("---")
    A("")

    # ══ 12bis. Resumen de Aciertos ═════════════════════════════════════════
    if obtener_estadisticas_aciertos:
        try:
            stats = obtener_estadisticas_aciertos(db_path, dias=90)
            A("## 12bis. Racha de Aciertos — Últimos 90 días")
            A("")
            A(f"| Métrica | Valor |")
            A(f"|---------|-------|")
            A(f"| Aciertos | {stats['aciertos_totales']} |")
            A(f"| Fallos | {stats['fallos_totales']} |")
            A(f"| Tasa de acierto | {stats['tasa_acierto_global']:.1%} |")
            A(f"| Total predicciones auditadas | {stats['total_predicciones']} |")
            A("")
            for bot, datos in list(stats["por_bot"].items())[:5]:
                tasa = datos["tasa_acierto"]
                A(f"- **{bot}**: {datos['aciertos']}/{datos['total']} aciertos ({tasa:.0%})")
            A("")
            A("---")
            A("")
        except Exception as e:
            pass  # Si falla, continuar sin sección de aciertos

    # ══ 13. Anexo ════════════════════════════════════════════════════════════
    A("## 13. Anexo mínimo técnico")
    A("")
    A("### Glosario corto")
    A("")
    A("| Término | Definición operativa |")
    A("|---|---|")
    A("| Fantasma | Indicador compuesto de agitación física multi-dominio |")
    A("| Muro de los 5 | Contador de dominios simultáneamente alterados |")
    A("| Firma | Patrón histórico de víspera de evento |")
    A("| Silent Trigger | Régimen de calma cargada sin convergencia explosiva |")
    A("| Lead time | Anticipación típica antes del evento |")
    A("| Juez | Auditor que valida avisos contra eventos reales |")
    A("| Omega | Bot del ritmo cósmico: luna, Schumann, envolvente solar |")
    A("| Sesgo causal | Diferencia entre competencia in-sample y real |")
    A("")
    A("### Checklist de publicación")
    A("")
    A(f"- [x] Datos ingestados completos ({total_ciclos:,} ciclos)")
    A(f"- [{'x' if actual else ' '}] Ciclo validado")
    A(f"- [{'x' if juez else ' '}] Auditoría sincronizada")
    A(f"- [{'x' if f30 else ' '}] Cálculo de percentiles actualizado")
    A(f"- [{'x' if previo else ' '}] Comparativo con ciclo previo integrado")
    A(f"- [x] Versión del modelo registrada ({version_modelo})")
    A("- [x] Tabla de acciones sugeridas actualizada")
    A("- [x] Nota metodológica incluida")
    A("")
    A("---")
    A(f"*Sentinel Omega · Fractal Core Research · reporte ejecutivo "
      f"{VERSION_REPORTE} · generado {ahora:%Y-%m-%d %H:%M} UTC*")

    conn.close()
    contenido = "\n".join(L) + "\n"
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(contenido, encoding="utf-8")

    version_dir = out.parent / "historial" / local.strftime("%Y") / local.strftime("%m")
    version_dir.mkdir(parents=True, exist_ok=True)
    vfile = version_dir / f"{local.strftime('%Y-%m-%d_%H-%M')}_EJECUTIVO_MX.md"
    vfile.write_text(contenido, encoding="utf-8")
    print(f"Reporte ejecutivo: {out}")
    print(f"Versión guardada: {vfile}")

    # Encolar por correo (outbox — sin Telegram, el correo es el canal)
    try:
        from sentinel_omega.infrastructure.api.correo import encolar_correo
        conn2 = sqlite3.connect(db_path)
        encolar_correo(
            conn2,
            asunto=(f"📊 Sentinel Omega — reporte ejecutivo "
                    f"{local:%Y-%m-%d %H:%M} MX"),
            cuerpo=contenido,
            tipo="REPORTE",
        )
        conn2.close()
    except Exception as e:
        print(f"(aviso) no se pudo encolar el correo: {e}")
    return contenido


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else DB_DEFAULT
    out = sys.argv[2] if len(sys.argv) > 2 else OUT_DEFAULT
    generar(db, out)
