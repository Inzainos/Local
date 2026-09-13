"""
Entrenamiento de firmas — two-phase training over the 30-year backcast.

Fase 1 (reconocimiento, sin castigo):
  For every significant event in the historical catalog, extract the
  pre-event window (14 days, 1H blocks) and register it as a firma for
  each bot over its own feature domain. Recurrence promotes signatures:
  nueva -> observada -> recurrente -> consolidada.

Fase 2 (backtest disciplinario):
  Re-present the member events of consolidated signatures. If the firma
  no longer recognizes the window that formed it (similarity below the
  alert threshold), the Juez records a FALLO — the bot forgot enforceable
  knowledge. New signatures are never punished.

Run via: python sentinel_omega/launcher.py --entrenar
"""

import json
import logging
import math
import sqlite3
import time as _time
from datetime import datetime
from typing import Dict, List, Optional

from sentinel_omega.core.firmas.signature_engine import (
    FEATURE_KEYS,
    SIMILARITY_ALERT,
    FirmaMemoria,
    extraer_features_ventana,
    similitud,
)
from sentinel_omega.core.juez.juez import Juez

logger = logging.getLogger(__name__)

# Los bots OBSERVAN todas las magnitudes (hasta el mínimo movimiento es un
# gatillo precursor), pero el sistema solo ALERTA y CASTIGA desde 4.5 para
# arriba: ese es el piso de firmas exigibles y de disciplina del Juez.
MIN_MAGNITUD_FIRMA = 4.5

# Mínimo observado en Fase 1: los bots registran firmas desde esta magnitud.
# Eventos M2.5–4.49 generan firmas pero NO activan disciplina (castigo/Juez
# solo punish) — solo alimentan el ACIERTO histórico del Juez.
MIN_MAGNITUD_OBSERVAR = 3.3   # piso de medición (= piso real del backcast); solo alerta desde 4.5

# Feature domain per bot — each bot only remembers what it measures.
# Padre keeps the full cross-domain vector (patterns within patterns).
BOT_FEATURES: Dict[str, Optional[List[str]]] = {
    "alfa1": ["bz_mean", "bz_min", "bz_deriv_std", "viento_avg", "viento_max",
              "proton_max", "bz_mean_72h"],
    "beta1": ["kp_mean", "kp_max", "schumann_mean", "schumann_std",
              "sismo_count_win", "sismo_max_mag_win", "fase_lunar",
              "es_sicigia", "kp_max_72h", "sismo_count_72h"],
    "beta2": ["so2_kt_win", "erupciones_win", "so2_kt_90d", "erupciones_90d"],
    "delta": ["btc_volatilidad", "btc_vol_max", "btc_ret_win", "btc_vol_72h"],
    # alfa2 entrena desde la tabla tbl_cobertura_satelital, que se acumula en
    # ciclos en vivo (no hay backcast de 14 años de cobertura ESA Sentinel).
    # Las firmas de alfa2 empiezan en 0 y crecen con el tiempo operativo.
    "alfa2": ["satellite_coverage_score", "satellite_thermal_anomalies",
              "satellite_clear_passes"],
    # Omega — el ritmo cósmico: fase lunar/sicigias + resonancia Schumann +
    # envolvente solar + acoplamiento Schumann↔mercado. Todo mapeado de la
    # telemetría existente (sin fetchers nuevos). Sus correlaciones viven en
    # tbl_correlaciones_omega, independientes de las del Padre.
    "omega": ["fase_lunar", "es_sicigia", "schumann_mean", "schumann_std",
              "kp_max", "kp_max_72h", "bz_min", "proton_max",
              "delta_schumann_coupling"],
    "padre": None,  # full vector
}

MIN_FEATURES_POR_BOT = {"alfa1": 3, "beta1": 3, "beta2": 4, "delta": 4,
                         "alfa2": 2, "omega": 4, "padre": 5}

# Each bot only trains inside its own historical window (data availability):
# beta2 = desde 2012 (catálogo volcánico NASA MSVOLSO2L4)
# delta = desde 2016 (BTC/cripto/tendencias)
# alfa2 NO tiene ventana de arranque fija: entrena solo desde la primera fila
# de tbl_cobertura_satelital (datos en vivo). El backcast no la incluye.
BOT_DESDE: Dict[str, str] = {
    "beta2": "2012-01-01",
    "delta": "2016-01-01",
}

# Bots que solo entrenan desde datos EN VIVO (no tienen backcast en la DB).
# El loop de Fase 1 los salta si la fuente es tbl_historico_sismico_raw
# sin filas de tbl_cobertura_satelital en el mismo periodo.
BOTS_LIVE_ONLY = {"alfa2"}


def _event_class(mag: float) -> str:
    if mag >= 7.0:
        return "SISMO_M7"
    if mag >= 6.0:
        return "SISMO_M6"
    if mag >= 5.0:
        return "SISMO_M5"
    if mag >= 4.5:
        return "SISMO_M4"      # 4.5–4.99: piso de alerta/castigo (exigible)
    if mag >= 4.0:
        return "SISMO_M4_obs"  # 4.0–4.49: observado, no exigible
    if mag >= 3.0:
        return "SISMO_M3_obs"  # 3.0–3.99: observado, no exigible
    return "SISMO_M2_obs"      # 2.0–2.99: observado, no exigible


def _event_class_volcanico(vei: float) -> str:
    """Volcanic event class by VEI (Volcanic Explosivity Index)."""
    if vei >= 5.0:
        return "ERUPCION_VEI5"
    if vei >= 4.0:
        return "ERUPCION_VEI4"
    return "ERUPCION_VEI3"


def _event_class_solar(kp_max: float) -> str:
    """Solar storm event class by Kp index (NOAA G-scale proxy)."""
    if kp_max >= 9.0:
        return "TORMENTA_Kp9"   # G5 extreme
    if kp_max >= 7.0:
        return "TORMENTA_Kp7"   # G3 strong
    return "TORMENTA_Kp6"       # G2 moderate


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def derivar_eventos_no_sismicos(conn: sqlite3.Connection) -> int:
    """Derive non-seismic event catalog from existing backcast tables.

    Volcanic: rows in tbl_desgasificacion_raw with vei >= 3.
    Solar storms: onset rows in tbl_clima_espacial_raw where kp_max >= 6.
    An onset is the first row in a consecutive block above the threshold;
    i.e., the previous row in the ordered dataset was NOT a storm. This
    relies on the hourly resolution of tbl_clima_espacial_raw — rows are
    consecutive 1-hour samples. If the data has gaps, the onset detection
    may still fire at the start of each gap-separated burst, which is
    acceptable (each burst is a distinct storm event).

    Stores to tbl_eventos_no_sismicos. Idempotent (INSERT OR IGNORE).
    Returns the number of rows actually inserted (not total attempts).
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tbl_eventos_no_sismicos "
        "(timestamp_blk TEXT NOT NULL, id_nodo INTEGER NOT NULL, "
        " event_class TEXT NOT NULL, fuente TEXT DEFAULT '', "
        " intensidad REAL DEFAULT 0.0, "
        " PRIMARY KEY (timestamp_blk, id_nodo, event_class))"
    )
    total = 0

    # ── Volcanic events ──────────────────────────────────────────────
    try:
        erupciones = conn.execute(
            "SELECT timestamp_blk, id_nodo, vei FROM tbl_desgasificacion_raw "
            "WHERE vei >= 3 ORDER BY timestamp_blk"
        ).fetchall()
        for ts, id_nodo, vei in erupciones:
            clase = _event_class_volcanico(float(vei))
            before = conn.total_changes
            conn.execute(
                "INSERT OR IGNORE INTO tbl_eventos_no_sismicos "
                "(timestamp_blk, id_nodo, event_class, fuente, intensidad) "
                "VALUES (?, ?, ?, 'tbl_desgasificacion_raw', ?)",
                (ts, id_nodo, clase, float(vei)),
            )
            total += conn.total_changes - before
        logger.info(f"  Eventos volcánicos derivados: {len(erupciones)}")
    except sqlite3.OperationalError:
        logger.info("  tbl_desgasificacion_raw sin datos VEI — saltando volcánicos")

    # ── Solar storm onset events (global → node 0) ───────────────────
    try:
        solar_rows = conn.execute(
            "SELECT timestamp_blk, kp_max FROM tbl_clima_espacial_raw "
            "WHERE kp_max IS NOT NULL ORDER BY timestamp_blk"
        ).fetchall()
        prev_storm = False
        n_solar = 0
        for ts, kp in solar_rows:
            if kp is None:
                prev_storm = False
                continue
            is_storm = float(kp) >= 6.0
            if is_storm and not prev_storm:
                clase = _event_class_solar(float(kp))
                conn.execute(
                    "INSERT OR IGNORE INTO tbl_eventos_no_sismicos "
                    "(timestamp_blk, id_nodo, event_class, fuente, intensidad) "
                    "VALUES (?, 0, ?, 'tbl_clima_espacial_raw', ?)",
                    (ts, clase, float(kp)),
                )
                n_solar += 1
                total += 1
            prev_storm = is_storm
        logger.info(f"  Tormentas solares derivadas (onset): {n_solar}")
    except sqlite3.OperationalError:
        logger.info("  tbl_clima_espacial_raw sin datos Kp — saltando tormentas solares")

    conn.commit()
    logger.info(f"Eventos no sísmicos derivados total: {total}")
    return total


def entrenar_reconocimiento(
    db_path: str,
    max_eventos: Optional[int] = None,
    bots: Optional[List[str]] = None,
) -> Dict:
    """Fase 1 — learn signatures from every observed historical event.

    Observes ALL magnitudes >= MIN_MAGNITUD_OBSERVAR (3.3): bots register
    firma patterns for every size of event so that small precursors are
    captured. The Juez logs an ACIERTO for every successful registration —
    this builds the positive pattern-history used by resumen_por_bot() even
    before Fase 2 discipline runs.

    Events below MIN_MAGNITUD_FIRMA (4.5) are non-enforceable: they generate
    firmas and Juez ACIERTOs but never trigger discipline (castigo).

    bots: restrict registration to these bots (e.g. ["beta2", "delta"] for
    an incremental training pass without inflating other bots' recurrence).
    """
    conn = sqlite3.connect(db_path)
    memoria = FirmaMemoria(conn)
    juez = Juez(conn)
    bots_activos = {
        b: k for b, k in BOT_FEATURES.items() if bots is None or b in bots
    }

    # If every active bot has a bounded window, skip events before the
    # earliest one (no bot would register them anyway).
    desde_global = None
    if bots is not None and all(b in BOT_DESDE for b in bots_activos):
        desde_global = min(BOT_DESDE[b] for b in bots_activos)

    query = (
        "SELECT timestamp_blk, id_nodo, sismo_max_mag "
        "FROM tbl_historico_sismico_raw "
        "WHERE sismo_max_mag >= ? "
    )
    params: tuple = (MIN_MAGNITUD_OBSERVAR,)
    if desde_global:
        query += "AND timestamp_blk >= ? "
        params = (MIN_MAGNITUD_OBSERVAR, desde_global)
    query += "ORDER BY timestamp_blk"
    eventos = conn.execute(query, params).fetchall()
    if max_eventos:
        eventos = eventos[:max_eventos]

    logger.info(
        f"=== FASE 1 RECONOCIMIENTO: {len(eventos)} eventos "
        f"M{MIN_MAGNITUD_OBSERVAR}+ (exigibles desde M{MIN_MAGNITUD_FIRMA}) ==="
    )

    stats = {"eventos": len(eventos), "firmas_nuevas": 0, "recurrencias": 0,
             "sin_datos": 0, "juez_aciertos": 0}

    import time as _time

    for idx, (ts_evento, id_nodo, mag) in enumerate(eventos):
        if idx % 1000 == 0 and idx > 0:
            logger.info(
                f"  Fase 1 progreso: {idx}/{len(eventos)} eventos "
                f"({stats['firmas_nuevas']} firmas, "
                f"{stats['recurrencias']} recurrencias)"
            )
        features = extraer_features_ventana(conn, ts_evento, id_nodo)
        if features is None:
            stats["sin_datos"] += 1
            continue

        clase = _event_class(mag)
        evento_ref = f"{ts_evento}|nodo{id_nodo}|M{mag:.1f}"
        bots_registrados: List[str] = []

        for bot, keys in bots_activos.items():
            # alfa2 (y cualquier bot live-only) NO tiene datos en el backcast;
            # sus firmas se acumulan desde ciclos operativos en tbl_cobertura_satelital.
            if bot in BOTS_LIVE_ONLY:
                continue
            desde = BOT_DESDE.get(bot)
            if desde and ts_evento < desde:
                continue  # event predates this bot's historical window
            sub = (
                features if keys is None
                else {k: v for k, v in features.items() if k in keys}
            )
            if len(sub) < MIN_FEATURES_POR_BOT[bot]:
                continue
            _, _, es_nueva = memoria.registrar(
                bot, clase, id_nodo, sub, evento_ref, ts_evento
            )
            if es_nueva:
                stats["firmas_nuevas"] += 1
            else:
                stats["recurrencias"] += 1
            bots_registrados.append(bot)

        # Juez: log ACIERTO for every bot that successfully registered a firma.
        # Uses ventana_h=0 so records resolve immediately (event is already known).
        # This builds the positive audit history from the learning phase onward.
        for bot in bots_registrados:
            juez.registrar_prediccion(
                bot_name=bot,
                prediccion="alert",
                confianza=1.0,
                ventana_h=0,
                detalles={
                    "fase": "reconocimiento",
                    "clase": clase,
                    "evento": evento_ref,
                    "mag": round(float(mag), 1),
                    "exigible": float(mag) >= MIN_MAGNITUD_FIRMA,
                },
                timestamp=_time.time(),
            )
        if bots_registrados:
            juez.evaluar_pendientes(
                evento_ocurrido=True,
                verdad=evento_ref,
                firma_conocida=False,  # Fase 1 is learning, not enforcement
                fase="reconocimiento",  # NUNCA resolver las vivas del launcher
            )
            stats["juez_aciertos"] += len(bots_registrados)

    stats["memoria"] = memoria.stats()
    logger.info(f"Fase 1 completa: {stats}")
    conn.close()
    return stats


def backtest_disciplinario(db_path: str, bots: Optional[List[str]] = None) -> Dict:
    """Fase 2 — el Padre castiga.

    Re-presents the member events of every consolidated signature:
      - Bot recognizes the pattern -> ACIERTO logged to Juez + mild refuerzo.
      - Bot fails to recognize enforceable knowledge (mag >= MIN_MAGNITUD_FIRMA)
        -> castigo hijo (x1): weight drops and the Juez records FALLO.
      - The Padre's own meta-signature fails -> castigo Padre (x2): double
        weight decay and double Juez severity (base_geo protocol).
      - Events below MIN_MAGNITUD_FIRMA are observed but NOT disciplined: Juez
        still records the FALLO pattern for audit, but castigar() is skipped so
        sub-threshold misses do not erode a bot's credibility weight.
    The adjusted weights persist in TBL_PESOS_BOTS and the Padre uses them
    to weigh each bot's vote in live consensus.
    """
    conn = sqlite3.connect(db_path)
    memoria = FirmaMemoria(conn)
    juez = Juez(conn)

    consolidadas = memoria.consolidadas()
    if bots is not None:
        consolidadas = [f for f in consolidadas if f["bot_name"] in bots]
    logger.info(
        f"=== FASE 2 DISCIPLINA: {len(consolidadas)} firmas consolidadas ==="
    )

    stats = {"firmas_evaluadas": 0, "reconocidas": 0, "fallos": 0,
             "castigos_hijo": 0, "castigos_padre": 0,
             "atencion_redistribuida": 0, "juez_aciertos": 0}

    from sentinel_omega.core.firmas.signature_engine import similitud
    from sentinel_omega.core.juez.pesos import (
        PESO_MAX, castigar, reforzar, cargar_pesos,
    )

    import time as _time

    # evento_ref -> {bot: reconoció} — needed for attention redistribution
    resultados_por_evento: Dict[str, Dict[str, bool]] = {}

    for firma in consolidadas:
        bot = firma["bot_name"]
        es_padre = bot == "padre"

        # Eventos desde la tabla hija normalizada (1NF).
        eventos = [
            r[0] for r in conn.execute(
                "SELECT evento_ref FROM tbl_firma_eventos "
                "WHERE firma_id = ? ORDER BY orden",
                (firma["firma_id"],),
            )
        ]

        for ref in eventos:
            try:
                ts_evento, nodo_part, mag_part = ref.split("|")
                id_nodo = int(nodo_part.replace("nodo", ""))
                # mag_part may be "M6.4" (seismic) or "ERUPCION_VEI4:4.0" (non-seismic)
                mag_str = mag_part.replace("M", "").split(":")[0]
                magnitud = float(mag_str)
            except (ValueError, IndexError):
                continue

            # base_geo: gravity scales with event size above the enforcement floor
            # (M5 -> 1, M6 -> 2, M7 -> 3); sub-threshold events stay at 1.0
            gravedad = 1.0 + max(0.0, magnitud - MIN_MAGNITUD_FIRMA)
            es_exigible = magnitud >= MIN_MAGNITUD_FIRMA

            features = extraer_features_ventana(conn, ts_evento, id_nodo)
            if features is None:
                continue

            keys = BOT_FEATURES.get(bot)
            sub = (
                features if keys is None
                else {k: v for k, v in features.items() if k in keys}
            )
            sim = similitud(sub, firma["features"])
            stats["firmas_evaluadas"] += 1
            reconocio = sim >= SIMILARITY_ALERT
            resultados_por_evento.setdefault(ref, {})[bot] = reconocio

            if reconocio:
                stats["reconocidas"] += 1
                reforzar(conn, bot)
                # Log ACIERTO so resumen_por_bot() and asertividad reflect
                # successful recognitions, not just failures.
                juez.registrar_prediccion(
                    bot_name=bot,
                    prediccion="alert",
                    confianza=round(sim, 3),
                    ventana_h=0,
                    detalles={
                        "fase": "backtest",
                        "firma_id": firma["firma_id"],
                        "evento": ref,
                        "similitud": round(sim, 3),
                        "gravedad": round(gravedad, 2),
                    },
                    timestamp=_time.time(),
                )
                juez.evaluar_pendientes(
                    evento_ocurrido=True,
                    verdad=ref,
                    firma_conocida=es_exigible,
                    fase="backtest",
                )
                stats["juez_aciertos"] += 1
            else:
                stats["fallos"] += 1
                # Only discipline (weight penalty) for enforceable events.
                # Sub-threshold misses are recorded for auditing but do not
                # erode the bot's credibility.
                if es_exigible:
                    castigar(conn, bot, es_padre=es_padre, gravedad=gravedad)
                    if es_padre:
                        stats["castigos_padre"] += 1
                    else:
                        stats["castigos_hijo"] += 1

                juez.registrar_prediccion(
                    bot_name=bot,
                    prediccion="no_signal",
                    confianza=0.0,
                    ventana_h=0,
                    detalles={
                        "fase": "backtest",
                        "firma_id": firma["firma_id"],
                        "evento": ref,
                        "similitud": round(sim, 3),
                        "gravedad": round(gravedad, 2),
                        "exigible": es_exigible,
                    },
                )
                juez.evaluar_pendientes(
                    evento_ocurrido=True,
                    verdad=ref,
                    firma_conocida=es_exigible,
                    multiplicador=2.0 if es_padre else 1.0,
                    gravedad=gravedad,
                    fase="backtest",
                )

    # base_geo: when the Padre missed an event that a subordinate DID see,
    # the punished Padre is forced to give more attention weight to the bot
    # that was right — extra reinforcement for that bot.
    for ref, resultados in resultados_por_evento.items():
        if resultados.get("padre") is False:
            for bot, reconocio in resultados.items():
                if bot != "padre" and reconocio:
                    reforzar(conn, bot, hasta=PESO_MAX)
                    stats["atencion_redistribuida"] += 1
                    logger.info(
                        f"ATENCIÓN REDISTRIBUIDA: {bot} vio {ref} que el "
                        f"Padre ignoró — refuerzo extra"
                    )

    stats["auditoria"] = juez.resumen_por_bot()
    stats["pesos"] = cargar_pesos(conn)

    # Aligerar el historial: el backtest evaluó TODO el catálogo para ajustar
    # los pesos y calcular la reincidencia, pero esos FALLOs son transitorios
    # y se regeneran en cada entrenamiento. Ya cumplieron su función — nos
    # quedamos con lo significativo (los pesos + las predicciones VIVAS) y
    # podamos el registro del backtest para que el ledger no crezca sin fin.
    # Por columna fase (estricta) — las filas 'viva' JAMÁS se tocan: la
    # auditoría viva es append-only (PENDIENTE→resuelto, nunca DELETE).
    podados = conn.execute(
        "DELETE FROM TBL_JUEZ_AUDITORIA WHERE fase = 'backtest'"
    ).rowcount
    conn.commit()
    stats["auditoria_backtest_podada"] = podados

    logger.info(f"Fase 2 completa: {stats}")
    conn.close()
    return stats


def entrenar(db_path: str, max_eventos: Optional[int] = None) -> Dict:
    """Full training run: Fase 1 (seismic) + Fase 1b (non-seismic) + Fase 2 + lags + correlaciones.

    Envuelto en la medición del sesgo de aprendizaje (realidad vs fantasía):
    se mide ANTES del pre-entrenamiento (línea base, sin castigo) y DESPUÉS
    de la disciplina (con castigo si la decisión real sigue floja), y se
    reporta cuánto mejoró el reconocimiento CAUSAL de cada bot con esta
    corrida — la diferencia entre las decisiones antes y después de aprender.
    """
    from sentinel_omega.infrastructure.pipeline.mantenimiento import (
        evaluar_sesgo_aprendizaje,
    )

    # PRE: línea base sin disciplinar (¿qué tan real era su competencia antes?)
    sesgo_pre = {}
    try:
        sesgo_pre = evaluar_sesgo_aprendizaje(db_path, aplicar_castigo=False)
        logger.info(f"Sesgo PRE-entrenamiento (línea base): {sesgo_pre.get('por_bot')}")
    except Exception as e:
        logger.warning(f"Sesgo pre-entrenamiento no disponible: {e}")

    fase1 = entrenar_reconocimiento(db_path, max_eventos=max_eventos)
    fase1b = entrenar_reconocimiento_no_sismico(db_path, max_eventos=max_eventos)
    fase2 = backtest_disciplinario(db_path)
    lags = calcular_lags_anticipacion(db_path)
    correlaciones = calcular_correlaciones_evento(db_path)

    # Entrenamiento cimático: graba en tbl_cimatica_patrones la telemetría
    # de la víspera de cada evento histórico con frecuencias ya contadas —
    # la cimática viva no empieza de cero.
    cimatica_stats = {}
    try:
        from sentinel_omega.core.firmas.cimatica import entrenar_cimatica
        cimatica_stats = entrenar_cimatica(db_path, max_eventos=max_eventos)
    except Exception as e:
        logger.warning(f"Entrenamiento cimático no disponible: {e}")

    # POST: medición disciplinaria (castiga al Padre/Omega si lo real no mejora)
    sesgo_post = {}
    mejora = {}
    try:
        sesgo_post = evaluar_sesgo_aprendizaje(db_path, aplicar_castigo=True)
        pre_bots = sesgo_pre.get("por_bot", {})
        for bot, d in sesgo_post.get("por_bot", {}).items():
            antes = pre_bots.get(bot, {}).get("causal")
            if antes is not None:
                mejora[bot] = round(d["causal"] - antes, 4)
        logger.info(f"Mejora causal por bot (post - pre): {mejora}")
    except Exception as e:
        logger.warning(f"Sesgo post-entrenamiento no disponible: {e}")

    return {"fase1": fase1, "fase1b": fase1b, "fase2": fase2, "lags": lags,
            "correlaciones": correlaciones,
            "cimatica": cimatica_stats,
            "sesgo_pre": sesgo_pre.get("por_bot", {}),
            "sesgo_post": sesgo_post.get("por_bot", {}),
            "mejora_causal": mejora}


# Offsets probados: la ventana de la firma termina N horas ANTES del evento.
# El lag de un evento es el offset MÁS TEMPRANO donde la firma ya se reconocía.
LAG_OFFSETS_H = [336, 240, 168, 120, 72, 24]
LAG_MUESTRA_POR_CLASE = 150


def calcular_lags_anticipacion(db_path: str) -> Dict:
    """Average anticipation lead time per event class (in-sample).

    For consolidated Padre signatures, re-test each member event with the
    window shifted back in time: if the signature already matched 7 days
    before the event, the system had ~7 days of warning. Persisted to
    tbl_lag_anticipacion for the report.
    """
    from datetime import datetime as _dt, timedelta as _td
    from sentinel_omega.core.firmas.signature_engine import similitud

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tbl_lag_anticipacion ("
        "event_class TEXT PRIMARY KEY, lag_promedio_h REAL, lag_max_h REAL, "
        "lag_min_h REAL, n_eventos INTEGER, "
        "updated_at TEXT DEFAULT (datetime('now')))"
    )

    memoria = FirmaMemoria(conn)
    consolidadas = [
        f for f in memoria.consolidadas() if f["bot_name"] == "padre"
    ]

    lags_por_clase: Dict[str, List[float]] = {}
    evaluados_por_clase: Dict[str, int] = {}

    for firma in consolidadas:
        clase = firma["event_class"]
        if evaluados_por_clase.get(clase, 0) >= LAG_MUESTRA_POR_CLASE:
            continue
        # Muestra de 3 eventos desde la tabla hija (no cargamos el array entero).
        eventos = [
            r[0] for r in conn.execute(
                "SELECT evento_ref FROM tbl_firma_eventos "
                "WHERE firma_id = ? ORDER BY orden LIMIT 3",
                (firma["firma_id"],),
            )
        ]

        lags_firma: List[float] = []
        for ref in eventos:  # muestra por firma (ya viene limitada a 3)
            if evaluados_por_clase.get(clase, 0) >= LAG_MUESTRA_POR_CLASE:
                break
            try:
                ts_evento, nodo_part, _ = ref.split("|")
                id_nodo = int(nodo_part.replace("nodo", ""))
                t0 = _dt.strptime(ts_evento, "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            evaluados_por_clase[clase] = evaluados_por_clase.get(clase, 0) + 1
            lag_detectado = None
            for offset_h in LAG_OFFSETS_H:  # earliest first
                ts_shift = (t0 - _td(hours=offset_h)).strftime("%Y-%m-%d %H:%M")
                features = extraer_features_ventana(conn, ts_shift, id_nodo)
                if features is None:
                    continue
                if similitud(features, firma["features"]) >= SIMILARITY_ALERT:
                    lag_detectado = float(offset_h)
                    break  # earliest matching offset = max anticipation
            if lag_detectado is not None:
                lags_por_clase.setdefault(clase, []).append(lag_detectado)
                lags_firma.append(lag_detectado)

        # Per-signature lead time: THIS firma's own typical window
        if lags_firma:
            conn.execute(
                "UPDATE TBL_FIRMAS SET lag_promedio_h = ?, lag_n = ? "
                "WHERE firma_id = ?",
                (sum(lags_firma) / len(lags_firma), len(lags_firma),
                 firma["firma_id"]),
            )

    resultado = {}
    for clase, lags in lags_por_clase.items():
        prom = sum(lags) / len(lags)
        conn.execute(
            "INSERT OR REPLACE INTO tbl_lag_anticipacion "
            "(event_class, lag_promedio_h, lag_max_h, lag_min_h, n_eventos, "
            " updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (clase, prom, max(lags), min(lags), len(lags)),
        )
        resultado[clase] = {
            "lag_promedio_dias": round(prom / 24, 1),
            "lag_max_dias": round(max(lags) / 24, 1),
            "n": len(lags),
        }
    conn.commit()
    conn.close()
    logger.info(f"Lags de anticipación: {resultado}")

    factores = analizar_factores_lag(db_path)
    resultado["factores"] = factores
    return resultado


def analizar_factores_lag(db_path: str) -> Dict:
    """What do slow-warning firmas share vs fast-warning ones?

    Splits per-firma lags into terciles (rápidas = shortest lead, lentas =
    longest lead) and compares each feature's mean between groups. The top
    differentiating factors reveal WHY some events announce themselves
    earlier — persisted to tbl_factores_lag for the report and, in time,
    for predicting a match's expected delay from its own features.
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tbl_factores_lag ("
        "feature TEXT PRIMARY KEY, media_rapidas REAL, media_lentas REAL, "
        "diferencia_norm REAL, updated_at TEXT DEFAULT (datetime('now')))"
    )

    rows = conn.execute(
        "SELECT features_json, lag_promedio_h FROM TBL_FIRMAS "
        "WHERE bot_name = 'padre' AND estado = 'consolidada' "
        "AND lag_promedio_h IS NOT NULL ORDER BY lag_promedio_h"
    ).fetchall()
    if len(rows) < 9:  # need enough firmas for terciles to mean anything
        conn.close()
        return {}

    tercio = len(rows) // 3
    rapidas = [json.loads(r[0]) for r in rows[:tercio]]
    lentas = [json.loads(r[0]) for r in rows[-tercio:]]

    def _media(grupo: List[Dict], key: str) -> Optional[float]:
        vals = [g[key] for g in grupo if key in g]
        return sum(vals) / len(vals) if len(vals) >= max(3, len(grupo) // 3) else None

    factores = []
    for key in FEATURE_KEYS:
        mr, ml = _media(rapidas, key), _media(lentas, key)
        if mr is None or ml is None:
            continue
        escala = (abs(mr) + abs(ml)) / 2
        if escala < 1e-9:
            continue
        diff = (ml - mr) / escala  # >0: higher in slow-warning firmas
        factores.append((key, mr, ml, diff))

    factores.sort(key=lambda f: -abs(f[3]))
    for key, mr, ml, diff in factores:
        conn.execute(
            "INSERT OR REPLACE INTO tbl_factores_lag "
            "(feature, media_rapidas, media_lentas, diferencia_norm, "
            " updated_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (key, mr, ml, diff),
        )
    conn.commit()

    lag_stats = conn.execute(
        "SELECT MIN(lag_promedio_h), AVG(lag_promedio_h), MAX(lag_promedio_h), "
        "COUNT(*) FROM TBL_FIRMAS WHERE bot_name='padre' "
        "AND lag_promedio_h IS NOT NULL"
    ).fetchone()
    conn.close()

    top = {
        f[0]: {"rapidas": round(f[1], 2), "lentas": round(f[2], 2),
               "dif": round(f[3], 2)}
        for f in factores[:6]
    }
    logger.info(f"Factores de lag (top): {top}")
    return {
        "firmas_con_lag": lag_stats[3],
        "lag_dias": {
            "min": round(lag_stats[0] / 24, 1),
            "prom": round(lag_stats[1] / 24, 1),
            "max": round(lag_stats[2] / 24, 1),
        },
        "top_factores": top,
    }


def entrenar_reconocimiento_no_sismico(
    db_path: str,
    max_eventos: Optional[int] = None,
    bots: Optional[List[str]] = None,
) -> Dict:
    """Fase 1b — learn signatures from non-seismic natural events.

    Trains on volcanic eruptions (VEI≥3, from tbl_desgasificacion_raw) and
    solar storm onsets (Kp≥6, from tbl_clima_espacial_raw). Both are derived
    from existing backcast tables via derivar_eventos_no_sismicos() and stored
    in tbl_eventos_no_sismicos before the training loop runs.

    Uses the same feature extraction and firma registration as Fase 1 —
    the same 14-day pre-event window — so bots learn what precedes eruptions
    and solar storms, not just earthquakes.

    The Padre's full-vector signatures will now capture financial (Delta) and
    atmospheric (Beta-2) patterns that precede these events too, enabling
    the correlation heatmap to reveal cross-domain relationships.
    """
    conn = sqlite3.connect(db_path)

    # Derive if table is absent or empty
    n_previos = 0
    if _table_exists(conn, "tbl_eventos_no_sismicos"):
        n_previos = conn.execute(
            "SELECT COUNT(*) FROM tbl_eventos_no_sismicos"
        ).fetchone()[0]
    if n_previos == 0:
        derivar_eventos_no_sismicos(conn)

    eventos = conn.execute(
        "SELECT timestamp_blk, id_nodo, event_class, intensidad "
        "FROM tbl_eventos_no_sismicos ORDER BY timestamp_blk"
    ).fetchall()
    if max_eventos:
        eventos = eventos[:max_eventos]

    memoria = FirmaMemoria(conn)
    bots_activos = {
        b: k for b, k in BOT_FEATURES.items() if bots is None or b in bots
    }

    logger.info(
        f"=== FASE 1b RECONOCIMIENTO NO SÍSMICO: {len(eventos)} eventos ==="
    )
    stats = {"eventos": len(eventos), "firmas_nuevas": 0, "recurrencias": 0,
             "sin_datos": 0}

    for idx, (ts_evento, id_nodo, event_class, intensidad) in enumerate(eventos):
        if idx % 500 == 0 and idx > 0:
            logger.info(
                f"  Fase 1b progreso: {idx}/{len(eventos)} "
                f"({stats['firmas_nuevas']} firmas, "
                f"{stats['recurrencias']} recurrencias)"
            )
        features = extraer_features_ventana(conn, ts_evento, id_nodo)
        if features is None:
            stats["sin_datos"] += 1
            continue

        evento_ref = f"{ts_evento}|nodo{id_nodo}|{event_class}:{intensidad:.1f}"

        for bot, keys in bots_activos.items():
            if bot in BOTS_LIVE_ONLY:
                continue
            desde = BOT_DESDE.get(bot)
            if desde and ts_evento < desde:
                continue
            sub = (
                features if keys is None
                else {k: v for k, v in features.items() if k in keys}
            )
            if len(sub) < MIN_FEATURES_POR_BOT[bot]:
                continue
            _, _, es_nueva = memoria.registrar(
                bot, event_class, id_nodo, sub, evento_ref, ts_evento
            )
            if es_nueva:
                stats["firmas_nuevas"] += 1
            else:
                stats["recurrencias"] += 1

    stats["memoria"] = memoria.stats()
    logger.info(f"Fase 1b completa: {stats}")
    conn.close()
    return stats


def calcular_correlaciones_evento(db_path: str) -> Dict:
    """Compute feature × event_class correlation matrix from TBL_FIRMAS.

    For every (event_class, feature) pair, computes the mean feature value
    across all firmas of that class and normalises by the global mean across
    ALL classes. A ratio > 1 means the feature tends to be elevated in the
    14-day window before that event type; a ratio < 1 means it is suppressed.

    The resulting matrix is stored in tbl_patrones_correlacion and is used by
    the report generator to render the correlation heatmap. Re-running is safe
    (INSERT OR REPLACE).
    """
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tbl_patrones_correlacion "
        "(event_class TEXT NOT NULL, feature TEXT NOT NULL, "
        " media REAL DEFAULT 0.0, global_media REAL DEFAULT 0.0, "
        " ratio REAL DEFAULT 1.0, n_firmas INTEGER DEFAULT 0, "
        " updated_at TEXT DEFAULT (datetime('now')), "
        " PRIMARY KEY (event_class, feature))"
    )

    rows = conn.execute(
        "SELECT event_class, features_json FROM TBL_FIRMAS"
    ).fetchall()

    # Aggregate per (event_class, feature) and globally
    class_feat: Dict[str, Dict[str, list]] = {}
    global_feat: Dict[str, list] = {k: [] for k in FEATURE_KEYS}

    for event_class, features_json in rows:
        try:
            feats = json.loads(features_json)
        except Exception:
            continue
        cf = class_feat.setdefault(event_class, {k: [] for k in FEATURE_KEYS})
        for feat in FEATURE_KEYS:
            v = feats.get(feat)
            if v is None or math.isnan(float(v)) if isinstance(v, (int, float)) else True:
                continue
            cf[feat].append(float(v))
            global_feat[feat].append(float(v))

    global_means = {
        feat: sum(vals) / len(vals)
        for feat, vals in global_feat.items() if vals
    }

    resultado: Dict[str, Dict[str, float]] = {}
    for event_class, feat_lists in class_feat.items():
        resultado[event_class] = {}
        for feat, vals in feat_lists.items():
            if not vals:
                continue
            media = sum(vals) / len(vals)
            gm = global_means.get(feat, 0.0)
            ratio = media / gm if abs(gm) > 1e-9 else 1.0
            conn.execute(
                "INSERT OR REPLACE INTO tbl_patrones_correlacion "
                "(event_class, feature, media, global_media, ratio, "
                " n_firmas, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
                (event_class, feat, round(media, 4), round(gm, 4),
                 round(ratio, 3), len(vals)),
            )
            resultado[event_class][feat] = round(ratio, 3)

    conn.commit()
    conn.close()
    n_classes = len(resultado)
    n_pairs = sum(len(v) for v in resultado.values())
    logger.info(
        f"Correlaciones calculadas: {n_classes} event classes, {n_pairs} pares"
    )
    return resultado


# ── Disciplina de trasfondo — "castigo desde abajo" ──────────────────────────
# Los bots ALERTAN y guardan firmas PERMANENTES desde M4.5 (memoria de 32 años).
# Pero para que no se duerman con los precursores chiquitos, se les disciplina
# cada cierto tiempo contra sismos MENORES (M3.3–4.49) de un bloque reciente de
# años. Esas firmas viven en una tabla TEMPORAL que se poda por edad — solo
# sobreviven los PESOS neuronales. El ajuste de peso por corrida está ACOTADO
# para no cráterizar la credibilidad de un bot de un golpe.
MAG_MENOR_MIN = 3.3   # piso de medición vivo, alineado al backcast (alerta solo desde 4.5)
MAG_MENOR_MAX = MIN_MAGNITUD_FIRMA          # 4.5 — justo por debajo del piso de alerta
DISCIPLINA_MAX_EVENTOS = 300                # muestreo acotado por corrida
DISCIPLINA_RETENCION_DIAS = 90             # poda rolling de la tabla temporal
DISCIPLINA_MAX_AJUSTES = 3                  # pasos de peso por bot por corrida


def _fetch_sismos_menores(anio: int, mag_min: float, mag_max: float,
                          max_results: int = 20000) -> List[tuple]:
    """USGS por rango de fecha+magnitud (bloque histórico, no ventana viva)."""
    import requests
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": f"{anio}-01-01",
        "endtime": f"{anio}-12-31T23:59:59",
        "minmagnitude": mag_min,
        "maxmagnitude": mag_max,
        "limit": max_results,
        "orderby": "time",
    }
    try:
        r = requests.get(url, params=params, timeout=90)
        r.raise_for_status()
        out = []
        for f in r.json().get("features", []):
            props = f.get("properties", {})
            coords = (f.get("geometry") or {}).get("coordinates", [None, None, None])
            mag, lon, lat, t = props.get("mag"), coords[0], coords[1], props.get("time")
            if mag is None or lat is None or lon is None or t is None:
                continue
            ts = datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m-%d %H:%M")
            out.append((ts, lat, lon, float(mag)))
        return out
    except Exception as e:
        logger.warning(f"Disciplina de trasfondo: fetch USGS falló: {e}")
        return []


def disciplina_trasfondo(db_path: str, anio: Optional[int] = None,
                         max_eventos: int = DISCIPLINA_MAX_EVENTOS) -> Dict:
    """Castigo desde abajo — disciplina rolling contra sismos menores.

    No toca la memoria permanente (TBL_FIRMAS): las firmas menores van a
    tbl_firmas_menores (temporal, podada por edad). Solo persisten los pesos.

    El Juez registra un ACIERTO o FALLO por cada par bot × evento evaluado,
    para que su historial refleje también la vigilancia de precursores pequeños.
    Esos registros llevan fase="trasfondo" y NO se podan al terminar —
    son parte del historial de patrones del Juez.
    """
    from sentinel_omega.core.juez.pesos import castigar, reforzar
    from sentinel_omega.core.shared.geometria_uvg import nodo_mas_cercano

    import time as _time

    conn = sqlite3.connect(db_path)
    juez = Juez(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tbl_firmas_menores ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, bot_name TEXT, event_class TEXT, "
        "id_nodo INTEGER, mag REAL, features_json TEXT, ts_evento TEXT, "
        "creada_at TEXT DEFAULT (datetime('now')))"
    )
    # Poda rolling: fuera las firmas menores más viejas que la retención.
    conn.execute(
        "DELETE FROM tbl_firmas_menores WHERE creada_at < datetime('now', ?)",
        (f"-{DISCIPLINA_RETENCION_DIAS} days",),
    )
    conn.commit()

    # Bloque reciente = último año con contexto en el backcast.
    if anio is None:
        maxblk = conn.execute(
            "SELECT MAX(timestamp_blk) FROM tbl_clima_espacial_raw"
        ).fetchone()[0]
        anio = int(maxblk[:4]) if maxblk else datetime.utcnow().year - 1

    eventos = _fetch_sismos_menores(anio, MAG_MENOR_MIN, MAG_MENOR_MAX)
    if not eventos:
        conn.close()
        return {"anio": anio, "eventos": 0, "nota": "sin datos de sismos menores"}
    if len(eventos) > max_eventos:                 # muestreo uniforme
        paso = len(eventos) / max_eventos
        eventos = [eventos[int(i * paso)] for i in range(max_eventos)]

    memoria = FirmaMemoria(conn)
    consolidadas = {b: memoria.consolidadas(b) for b in BOT_FEATURES}
    conteo = {b: {"evaluadas": 0, "reconocidas": 0} for b in BOT_FEATURES}

    for ts, lat, lon, mag in eventos:
        nodo = nodo_mas_cercano(lat, lon)["id"]
        feats = extraer_features_ventana(conn, ts, nodo)
        if feats is None:
            continue
        clase = f"SISMO_M{int(mag)}"               # M2 / M3 / M4 (menores)
        evento_ref = f"{ts}|nodo{nodo}|M{mag:.1f}"
        bots_acierto: List[str] = []
        bots_fallo: List[str] = []

        for bot, keys in BOT_FEATURES.items():
            # alfa2 no tiene backcast → sus firmas consolidadas estarán vacías
            # durante el entrenamiento inicial; saltarlo evita falsos cero.
            if bot in BOTS_LIVE_ONLY:
                continue
            firmas_bot = consolidadas.get(bot) or []
            if not firmas_bot:
                continue
            sub = feats if keys is None else {k: feats[k] for k in keys if k in feats}
            if not sub:
                continue
            # Reconocimiento ESPACIAL: ¿la memoria del bot PARA ESE NODO
            # anticipó el chiquito ahí? Sin firma en el nodo = ceguera local.
            firmas_nodo = [f for f in firmas_bot if f["id_nodo"] == nodo]
            best = max((similitud(sub, f["features"]) for f in firmas_nodo),
                       default=0.0)
            conteo[bot]["evaluadas"] += 1
            if best >= SIMILARITY_ALERT:
                conteo[bot]["reconocidas"] += 1
                bots_acierto.append(bot)
            else:
                bots_fallo.append(bot)
            conn.execute(
                "INSERT INTO tbl_firmas_menores "
                "(bot_name, event_class, id_nodo, mag, features_json, ts_evento) "
                "VALUES (?,?,?,?,?,?)",
                (bot, clase, nodo, mag, json.dumps(sub), ts),
            )

        # Juez: log per-bot verdict for this minor event.
        now = _time.time()
        for bot in bots_acierto:
            juez.registrar_prediccion(
                bot_name=bot, prediccion="alert", confianza=1.0,
                ventana_h=0,
                detalles={"fase": "trasfondo", "clase": clase,
                          "evento": evento_ref, "mag": round(float(mag), 1)},
                timestamp=now,
            )
        for bot in bots_fallo:
            juez.registrar_prediccion(
                bot_name=bot, prediccion="no_signal", confianza=0.0,
                ventana_h=0,
                detalles={"fase": "trasfondo", "clase": clase,
                          "evento": evento_ref, "mag": round(float(mag), 1)},
                timestamp=now,
            )
        if bots_acierto or bots_fallo:
            juez.evaluar_pendientes(
                evento_ocurrido=True,
                verdad=evento_ref,
                firma_conocida=False,  # minor events are never enforceable
                fase="trasfondo",
            )

    # Ajuste de pesos ACOTADO por bot: más ceguera a los chiquitos → más castigo
    # (hasta DISCIPLINA_MAX_AJUSTES pasos), el resto se convierte en refuerzo.
    ajustes = {}
    for bot, c in conteo.items():
        if c["evaluadas"] == 0:
            continue
        tasa = c["reconocidas"] / c["evaluadas"]
        n_castigos = min(DISCIPLINA_MAX_AJUSTES,
                         round((1.0 - tasa) * DISCIPLINA_MAX_AJUSTES))
        n_refuerzos = DISCIPLINA_MAX_AJUSTES - n_castigos
        es_padre = bot == "padre"
        for _ in range(n_castigos):
            castigar(conn, bot, es_padre=es_padre, gravedad=1.0)
        for _ in range(n_refuerzos):
            reforzar(conn, bot)
        ajustes[bot] = {"reconocimiento": round(tasa, 3),
                        "castigos": n_castigos, "refuerzos": n_refuerzos}
    conn.commit()
    conn.close()
    logger.info(
        f"Disciplina de trasfondo ({anio}, M{MAG_MENOR_MIN}-{MAG_MENOR_MAX}, "
        f"{len(eventos)} eventos): {ajustes}"
    )
    return {"anio": anio, "eventos": len(eventos), "ajustes": ajustes}
