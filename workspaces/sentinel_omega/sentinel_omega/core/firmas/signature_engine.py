"""
Signature Engine — extracts, stores, promotes, and matches firmas.

Protocol (from sentinel_omega.docx):
  - A firma captures the pre-event window (default 14 days at 1H resolution)
    of all measured variables, plus a near sub-window (72h) for short-lead
    precursors.
  - New firmas are catalogued WITHOUT punishment. Promotion by recurrence:
      1 sighting  -> nueva
      2 sightings -> observada
      3-4         -> recurrente
      >= 5        -> consolidada  (enforceable knowledge)
  - In operation, bots compare the live state against consolidated firmas;
    a high-similarity match means "this looks like what preceded event X".
  - ZERO synthetic data: features are computed only from non-NULL backcast
    rows; missing variables simply stay absent from the vector.
"""

import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Fixed feature order — every firma vector uses these keys.
FEATURE_KEYS = [
    "bz_mean", "bz_min", "bz_deriv_std",
    "viento_avg", "viento_max",
    "kp_mean", "kp_max",
    "proton_max",
    "schumann_mean", "schumann_std",
    "sismo_count_win", "sismo_max_mag_win",
    "fase_lunar", "es_sicigia",
    "btc_volatilidad", "btc_vol_max", "btc_ret_win", "btc_vol_72h",
    "so2_kt_win", "erupciones_win", "so2_kt_90d", "erupciones_90d",
    # near sub-window (last 72h before the event)
    "bz_mean_72h", "kp_max_72h", "sismo_count_72h",
    # alfa2: cobertura satelital ESA Sentinel (live-only, acumulado desde ciclos)
    "satellite_coverage_score", "satellite_thermal_anomalies", "satellite_clear_passes",
    # delta_enriched: acoplamiento geofísico-financiero (live-only, desde tbl_delta_cross)
    "delta_cross_coupling", "delta_geo_coupling", "delta_schumann_coupling",
]

VENTANA_HORAS = 336  # 14 days
SUBVENTANA_HORAS = 72

SIMILARITY_MATCH = 0.85     # same firma family
SIMILARITY_ALERT = 0.80     # operational "looks like" threshold

# Cuántos avistamientos concretos se guardan por firma. Una firma que se
# repite 24,719 veces son 24,719 eventos CASI IDÉNTICOS (por eso matchean la
# misma firma) — guardarlos todos es puro bulto. Nos quedamos con una MUESTRA
# (los primeros N, que en entrenamiento cronológico son los más viejos → el
# min(ts) real se preserva) y el CONTEO fiel vive en `recurrencia`. Los tres
# lectores solo necesitan: min(ts) [orden=1], primeros 3 [lags], y una muestra
# para re-presentar [backtest] — todos cubiertos con N pequeño.
CAP_EVENTOS_MUESTRA = 10

ESTADO_POR_RECURRENCIA = [
    (5, "consolidada"),
    (3, "recurrente"),
    (2, "observada"),
    (1, "nueva"),
]


def _estado(recurrencia: int) -> str:
    for minimo, estado in ESTADO_POR_RECURRENCIA:
        if recurrencia >= minimo:
            return estado
    return "nueva"


def _stats(values: List[float]) -> Optional[Tuple[float, float, float, float]]:
    arr = np.array([v for v in values if v is not None], dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return None
    return float(arr.mean()), float(arr.min()), float(arr.max()), float(arr.std())


def extraer_features_ventana(
    conn: sqlite3.Connection,
    ts_evento: str,
    id_nodo: int,
) -> Optional[Dict[str, float]]:
    """Build the feature vector for the pre-event window ending at ts_evento.

    Reads the backcast tables (1H blocks). Returns None when the window has
    no space-weather coverage at all (nothing real to learn from).
    """
    q_win = (
        "SELECT bz_promedio, bz_min, bz_derivada, viento_solar_avg, "
        "viento_solar_max, kp_promedio, kp_max, proton_flux_10mev "
        "FROM tbl_clima_espacial_raw "
        "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?) "
        "ORDER BY timestamp_blk"
    )
    rows = conn.execute(
        q_win, (ts_evento, ts_evento, f"-{VENTANA_HORAS} hours")
    ).fetchall()
    if not rows:
        return None

    cols = list(zip(*rows))
    features: Dict[str, float] = {}

    bz = _stats(list(cols[0]))
    if bz:
        features["bz_mean"], features["bz_min"] = bz[0], bz[1]
    bz_deriv = _stats(list(cols[2]))
    if bz_deriv:
        features["bz_deriv_std"] = bz_deriv[3]
    viento = _stats(list(cols[3]))
    if viento:
        features["viento_avg"] = viento[0]
    viento_max = _stats(list(cols[4]))
    if viento_max:
        features["viento_max"] = viento_max[2]
    kp = _stats(list(cols[5]))
    if kp:
        features["kp_mean"] = kp[0]
    kp_max = _stats(list(cols[6]))
    if kp_max:
        features["kp_max"] = kp_max[2]
    protones = _stats(list(cols[7]))
    if protones:
        features["proton_max"] = protones[2]

    if not features:
        return None

    # Schumann per-window (node 0 = observation node feed)
    sch_rows = conn.execute(
        "SELECT schumann_hz FROM tbl_enjambre_telemetria "
        "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?)",
        (ts_evento, ts_evento, f"-{VENTANA_HORAS} hours"),
    ).fetchall()
    sch = _stats([r[0] for r in sch_rows])
    if sch:
        features["schumann_mean"], features["schumann_std"] = sch[0], sch[3]

    # Seismic context at the same node: foreshocks / quiescence / swarm
    sis = conn.execute(
        "SELECT COALESCE(SUM(sismo_count),0), COALESCE(MAX(sismo_max_mag),0) "
        "FROM tbl_historico_sismico_raw "
        "WHERE id_nodo = ? AND timestamp_blk < ? "
        "AND timestamp_blk >= datetime(?, ?)",
        (id_nodo, ts_evento, ts_evento, f"-{VENTANA_HORAS} hours"),
    ).fetchone()
    features["sismo_count_win"] = float(sis[0])
    features["sismo_max_mag_win"] = float(sis[1])

    # Lunar state at event time (tidal trigger context)
    luna = conn.execute(
        "SELECT fase_lunar_pct, es_sicigia FROM tbl_astronomia_cinematica "
        "WHERE timestamp_blk <= ? ORDER BY timestamp_blk DESC LIMIT 1",
        (ts_evento,),
    ).fetchone()
    if luna and luna[0] is not None:
        features["fase_lunar"] = float(luna[0])
        features["es_sicigia"] = float(luna[1] or 0)

    # Financial psyche (2014+) — Delta's domain: volatility pattern + net move
    btc = conn.execute(
        "SELECT volatilidad_24h, btc_precio_usd FROM tbl_psique_financiera "
        "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?) "
        "AND volatilidad_24h IS NOT NULL "
        "ORDER BY timestamp_blk",
        (ts_evento, ts_evento, f"-{VENTANA_HORAS} hours"),
    ).fetchall()
    btc_stats = _stats([r[0] for r in btc])
    if btc_stats:
        features["btc_volatilidad"] = btc_stats[0]
        features["btc_vol_max"] = btc_stats[2]
        precios = [r[1] for r in btc if r[1] is not None]
        if len(precios) >= 2 and precios[0]:
            features["btc_ret_win"] = (precios[-1] - precios[0]) / precios[0] * 100
        btc72 = conn.execute(
            "SELECT AVG(volatilidad_24h) FROM tbl_psique_financiera "
            "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?) "
            "AND volatilidad_24h IS NOT NULL",
            (ts_evento, ts_evento, f"-{SUBVENTANA_HORAS} hours"),
        ).fetchone()
        if btc72 and btc72[0] is not None:
            features["btc_vol_72h"] = float(btc72[0])

    # Volcanic degassing (Beta-2's domain) — global planetary SO2 state.
    # 14-day window + 90-day charge context. Zero eruptions in the window is
    # a real signal ONLY when the catalog is actually loaded — an empty table
    # would otherwise mint garbage all-zero signatures.
    try:
        catalogo = conn.execute(
            "SELECT COUNT(*) FROM tbl_desgasificacion_raw"
        ).fetchone()
        if not catalogo or catalogo[0] == 0:
            raise sqlite3.OperationalError("catalog empty")
        des = conn.execute(
            "SELECT COALESCE(SUM(so2_kt),0), COUNT(*) "
            "FROM tbl_desgasificacion_raw "
            "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?)",
            (ts_evento, ts_evento, f"-{VENTANA_HORAS} hours"),
        ).fetchone()
        des90 = conn.execute(
            "SELECT COALESCE(SUM(so2_kt),0), COUNT(*) "
            "FROM tbl_desgasificacion_raw "
            "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, '-90 days')",
            (ts_evento, ts_evento),
        ).fetchone()
        features["so2_kt_win"] = float(des[0])
        features["erupciones_win"] = float(des[1])
        features["so2_kt_90d"] = float(des90[0])
        features["erupciones_90d"] = float(des90[1])
    except sqlite3.OperationalError:
        pass  # table not present in this database

    # Near sub-window (last 72h)
    near = conn.execute(
        "SELECT AVG(bz_promedio), MAX(kp_max) FROM tbl_clima_espacial_raw "
        "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?)",
        (ts_evento, ts_evento, f"-{SUBVENTANA_HORAS} hours"),
    ).fetchone()
    if near and near[0] is not None:
        features["bz_mean_72h"] = float(near[0])
    if near and near[1] is not None:
        features["kp_max_72h"] = float(near[1])
    sis72 = conn.execute(
        "SELECT COALESCE(SUM(sismo_count),0) FROM tbl_historico_sismico_raw "
        "WHERE id_nodo = ? AND timestamp_blk < ? "
        "AND timestamp_blk >= datetime(?, ?)",
        (id_nodo, ts_evento, ts_evento, f"-{SUBVENTANA_HORAS} hours"),
    ).fetchone()
    features["sismo_count_72h"] = float(sis72[0])

    # Cobertura satelital alfa2 (tbl_cobertura_satelital).
    # Solo disponible desde que el sistema corre en vivo — si la tabla está
    # vacía (backcast o primer arranque) simplemente no se añaden estas features.
    try:
        sat = conn.execute(
            "SELECT coverage_score, thermal_anomalies, clear_passes "
            "FROM tbl_cobertura_satelital "
            "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?) "
            "ORDER BY timestamp_blk",
            (ts_evento, ts_evento, f"-{VENTANA_HORAS} hours"),
        ).fetchall()
        if sat:
            cov_scores = [r[0] for r in sat if r[0] is not None]
            thermal = [r[1] for r in sat if r[1] is not None]
            clear_p = [r[2] for r in sat if r[2] is not None]
            if cov_scores:
                features["satellite_coverage_score"] = float(
                    np.mean(cov_scores)
                )
            if thermal:
                features["satellite_thermal_anomalies"] = float(sum(thermal))
            if clear_p:
                features["satellite_clear_passes"] = float(sum(clear_p))
    except Exception:
        pass  # tabla no existe aún → features de alfa2 ausentes (NaN en vector)

    # Delta cross-correlation coupling (tbl_delta_cross).
    # Populated in live operation by the delta_enriched pipeline.
    # During backcast training these values are absent (NaN in vector) —
    # the system learns them incrementally from live cycles.
    try:
        dc = conn.execute(
            "SELECT AVG(cross_coupling), AVG(geomagnetic_coupling), "
            "AVG(schumann_coupling) "
            "FROM tbl_delta_cross "
            "WHERE timestamp_blk < ? AND timestamp_blk >= datetime(?, ?)",
            (ts_evento, ts_evento, f"-{VENTANA_HORAS} hours"),
        ).fetchone()
        if dc and dc[0] is not None:
            features["delta_cross_coupling"] = float(dc[0])
        if dc and dc[1] is not None:
            features["delta_geo_coupling"] = float(dc[1])
        if dc and dc[2] is not None:
            features["delta_schumann_coupling"] = float(dc[2])
    except Exception:
        pass  # tabla no existe aún → features delta_cross ausentes (NaN en vector)

    return features


def _vector(features: Dict[str, float]) -> np.ndarray:
    """Fixed-order vector; missing keys become NaN (excluded from similarity)."""
    return np.array(
        [features.get(k, np.nan) for k in FEATURE_KEYS], dtype=float
    )


def similitud(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Similarity in [0,1] over the features BOTH vectors actually have.

    Normalized inverse mean absolute z-difference. Missing (NaN) dimensions
    are excluded — never imputed (zero-synthetic rule).
    """
    va, vb = _vector(a), _vector(b)
    mask = ~(np.isnan(va) | np.isnan(vb))
    if mask.sum() < 4:  # too few shared dimensions to mean anything
        return 0.0
    va, vb = va[mask], vb[mask]
    scale = np.maximum(np.abs(va) + np.abs(vb), 1e-9) / 2.0
    diff = np.abs(va - vb) / scale
    return float(max(0.0, 1.0 - np.mean(np.minimum(diff, 2.0)) / 2.0))


class FirmaMemoria:
    """CRUD + promotion over TBL_FIRMAS. One instance per database."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def registrar(
        self,
        bot_name: str,
        event_class: str,
        id_nodo: Optional[int],
        features: Dict[str, float],
        evento_ref: str,
        ts_evento: str,
    ) -> Tuple[int, str, bool]:
        """Register a signature sighting.

        If it matches an existing firma of the same class (>= SIMILARITY_MATCH)
        the firma's recurrence rises, its features update as a running mean,
        and its state may promote. Otherwise a new firma is created.

        Returns (firma_id, estado, es_nueva).
        """
        rows = self._conn.execute(
            "SELECT firma_id, features_json, recurrencia, eventos_json "
            "FROM TBL_FIRMAS WHERE bot_name = ? AND event_class = ?",
            (bot_name, event_class),
        ).fetchall()

        best_id, best_sim, best_row = None, 0.0, None
        for row in rows:
            sim = similitud(features, json.loads(row[1]))
            if sim > best_sim:
                best_id, best_sim, best_row = row[0], sim, row

        if best_id is not None and best_sim >= SIMILARITY_MATCH:
            old_features = json.loads(best_row[1])
            recurrencia = best_row[2] + 1
            # Running mean over shared keys; keep keys only one side has.
            merged = dict(old_features)
            for k, v in features.items():
                if k in merged:
                    merged[k] = merged[k] + (v - merged[k]) / recurrencia
                else:
                    merged[k] = v
            estado = _estado(recurrencia)
            self._conn.execute(
                "UPDATE TBL_FIRMAS SET features_json = ?, recurrencia = ?, "
                "estado = ?, ultima_vista = ? WHERE firma_id = ?",
                (json.dumps(merged), recurrencia, estado, ts_evento, best_id),
            )
            # 1NF + muestreo: el evento es una FILA (append O(1)), y solo
            # guardamos los primeros CAP_EVENTOS_MUESTRA — el conteo fiel es
            # `recurrencia`. No escribimos la serie entera (era O(n²) y bulto).
            if recurrencia <= CAP_EVENTOS_MUESTRA:
                self._conn.execute(
                    "INSERT OR IGNORE INTO tbl_firma_eventos "
                    "(firma_id, evento_ref, ts_evento, orden) VALUES (?, ?, ?, ?)",
                    (best_id, evento_ref, ts_evento, recurrencia),
                )
            self._conn.commit()
            return best_id, estado, False

        cur = self._conn.execute(
            "INSERT INTO TBL_FIRMAS "
            "(bot_name, event_class, id_nodo, features_json, ventana_horas, "
            " recurrencia, estado, primera_vista, ultima_vista) "
            "VALUES (?, ?, ?, ?, ?, 1, 'nueva', ?, ?)",
            (bot_name, event_class, id_nodo, json.dumps(features),
             VENTANA_HORAS, ts_evento, ts_evento),
        )
        firma_id = cur.lastrowid
        self._conn.execute(
            "INSERT OR IGNORE INTO tbl_firma_eventos "
            "(firma_id, evento_ref, ts_evento, orden) VALUES (?, ?, ?, 1)",
            (firma_id, evento_ref, ts_evento),
        )
        self._conn.commit()
        return firma_id, "nueva", True

    def consolidadas(self, bot_name: Optional[str] = None) -> List[Dict[str, Any]]:
        q = ("SELECT firma_id, bot_name, event_class, id_nodo, features_json, "
             "recurrencia, estado FROM TBL_FIRMAS WHERE estado = 'consolidada'")
        params: tuple = ()
        if bot_name:
            q += " AND bot_name = ?"
            params = (bot_name,)
        return [
            {
                "firma_id": r[0], "bot_name": r[1], "event_class": r[2],
                "id_nodo": r[3], "features": json.loads(r[4]),
                "recurrencia": r[5], "estado": r[6],
            }
            for r in self._conn.execute(q, params).fetchall()
        ]

    def match_estado_actual(
        self,
        features: Dict[str, float],
        umbral: float = SIMILARITY_ALERT,
    ) -> List[Dict[str, Any]]:
        """Compare the live state against consolidated firmas.

        Returns matches sorted by similarity — "the current state looks
        similar (0.87) to the signature that preceded SISMO_M7 at node 45".
        """
        matches = []
        for firma in self.consolidadas():
            sim = similitud(features, firma["features"])
            if sim >= umbral:
                matches.append({
                    "firma_id": firma["firma_id"],
                    "event_class": firma["event_class"],
                    "id_nodo": firma["id_nodo"],
                    "similitud": round(sim, 3),
                    "recurrencia": firma["recurrencia"],
                })
        return sorted(matches, key=lambda m: -m["similitud"])

    def stats(self) -> Dict[str, int]:
        rows = self._conn.execute(
            "SELECT estado, COUNT(*) FROM TBL_FIRMAS GROUP BY estado"
        ).fetchall()
        out = {estado: n for estado, n in rows}
        out["total"] = sum(out.values())
        return out
