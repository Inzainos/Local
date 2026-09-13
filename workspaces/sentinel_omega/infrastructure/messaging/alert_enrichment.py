"""Enrichment helpers for Telegram alert/digest copy."""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple


def _as_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def format_lag_line(lag_h: Optional[float], lag_max_h: Optional[float] = None) -> str:
    """Human lag / anticipation window in Spanish."""
    lh = _as_float(lag_h)
    if lh is None or lh <= 0:
        return ""
    dias = lh / 24.0
    if dias >= 1.5:
        core = f"~{dias:.0f} días ({lh:.0f} h)"
    else:
        core = f"~{lh:.0f} h"
    extra = ""
    lm = _as_float(lag_max_h)
    if lm and lm > lh:
        extra = f" (hasta ~{lm/24:.0f} d)" if lm >= 36 else f" (hasta ~{lm:.0f} h)"
    hasta = (datetime.now(timezone.utc) + timedelta(hours=lh)).strftime("%d/%m %H:%M UTC")
    return f"⏱ <b>Lag / ventana típica:</b> {core}{extra} → vigilar hasta <code>{hasta}</code>"


def describe_values(tipo: str, values: Any) -> str:
    """Turn values_json into short Spanish bullets."""
    if values is None:
        return ""
    if isinstance(values, str):
        try:
            values = json.loads(values)
        except Exception:
            return str(values)[:200]
    if not isinstance(values, dict) or not values:
        return ""
    t = (tipo or "").upper()
    bits = []
    if "SEISMIC" in t or "SISMO" in t or "CLUSTER" in t:
        if values.get("event_count") is not None:
            bits.append(f"{values['event_count']} eventos en el enjambre")
        if values.get("max_magnitude") is not None:
            bits.append(f"máx M{float(values['max_magnitude']):.1f}")
        if values.get("total_events") is not None:
            bits.append(f"{values['total_events']} en ventana")
    elif "SILENT" in t or "CALMA" in t:
        if values.get("calm_duration_h") is not None:
            bits.append(f"calma geomagnética ~{float(values['calm_duration_h']):.0f} h")
        if values.get("kp_mean") is not None:
            bits.append(f"Kp medio {float(values['kp_mean']):.2f}")
        if values.get("kp_max") is not None:
            bits.append(f"Kp máx {float(values['kp_max']):.1f}")
    elif "SCHUMANN" in t:
        if values.get("schumann_hz") is not None:
            bits.append(f"{float(values['schumann_hz']):.2f} Hz")
        if values.get("activity") is not None or values.get("schumann_activity") is not None:
            act = values.get("activity", values.get("schumann_activity"))
            bits.append(f"actividad {float(act):.1f}")
    else:
        for k, v in list(values.items())[:6]:
            bits.append(f"{k}={v}")
    return " · ".join(str(b) for b in bits)


def nearest_nodo(conn: sqlite3.Connection, lat: float, lon: float) -> Optional[Dict[str, Any]]:
    try:
        rows = conn.execute(
            "SELECT node_id, nombre, lat, lon, region FROM TBL_NODOS_TOPOLOGIA "
            "WHERE activo IS NULL OR activo=1 OR activo=TRUE"
        ).fetchall()
    except Exception:
        try:
            rows = conn.execute(
                "SELECT node_id, nombre, lat, lon, region FROM TBL_NODOS_TOPOLOGIA"
            ).fetchall()
        except Exception:
            return None
    best = None
    best_d = 1e18
    for r in rows:
        try:
            nlat, nlon = float(r[2]), float(r[3])
        except Exception:
            continue
        # haversine km
        rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat, lon, nlat, nlon])
        dlat = rlat2 - rlat1
        dlon = rlon2 - rlon1
        a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
        d = 6371.0 * 2 * math.asin(math.sqrt(a))
        if d < best_d:
            best_d = d
            best = {
                "id_nodo": int(r[0]),
                "nodo_nombre": r[1],
                "lat": nlat,
                "lon": nlon,
                "region": r[4],
                "dist_km": round(d, 1),
            }
    return best


def epicentro_reciente(conn: sqlite3.Connection, hours: float = 72.0) -> Optional[Dict[str, Any]]:
    """Latest strongest quake in recent window from fuente table."""
    try:
        row = conn.execute(
            """
            SELECT time_utc, lat, lon, mag, id_nodo
            FROM tbl_eventos_sismicos_fuente
            WHERE time_utc >= datetime('now', ?)
            ORDER BY mag DESC, time_utc DESC
            LIMIT 1
            """,
            (f"-{int(hours)} hours",),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    out = {
        "time_utc": row[0],
        "lat": _as_float(row[1]),
        "lon": _as_float(row[2]),
        "mag": _as_float(row[3]),
        "id_nodo": row[4],
    }
    if out["id_nodo"] is not None:
        try:
            n = conn.execute(
                "SELECT nombre, region, lat, lon FROM TBL_NODOS_TOPOLOGIA WHERE node_id=?",
                (out["id_nodo"],),
            ).fetchone()
            if n:
                out["nodo_nombre"] = n[0]
                out["region"] = n[1]
                if out["lat"] is None:
                    out["lat"] = _as_float(n[2])
                if out["lon"] is None:
                    out["lon"] = _as_float(n[3])
        except Exception:
            pass
    if out.get("nodo_nombre") is None and out["lat"] is not None and out["lon"] is not None:
        nn = nearest_nodo(conn, out["lat"], out["lon"])
        if nn:
            out.update({k: nn[k] for k in ("id_nodo", "nodo_nombre", "region", "dist_km") if k in nn})
    return out


def lag_for_event_class(conn: sqlite3.Connection, event_class: Optional[str] = None) -> Tuple[Optional[float], Optional[float]]:
    if not event_class:
        # generic seismic lag if table exists
        event_class = "SISMO_M5"
    try:
        row = conn.execute(
            "SELECT lag_promedio_h, lag_max_h FROM tbl_lag_anticipacion WHERE event_class=? LIMIT 1",
            (event_class,),
        ).fetchone()
        if row:
            return _as_float(row[0]), _as_float(row[1])
    except Exception:
        pass
    try:
        row = conn.execute(
            "SELECT AVG(lag_promedio_h), MAX(lag_max_h) FROM tbl_lag_anticipacion"
        ).fetchone()
        if row and row[0] is not None:
            return _as_float(row[0]), _as_float(row[1])
    except Exception:
        pass
    return None, None


def enrich_precursor_row(
    conn: Optional[sqlite3.Connection],
    *,
    tipo: str,
    display_name: Optional[str] = None,
    station: Optional[str] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    values: Any = None,
    confidence: Any = None,
) -> Dict[str, Any]:
    """Build a rich precursor dict for templates / digest."""
    vals = values
    if isinstance(vals, str):
        try:
            vals = json.loads(vals)
        except Exception:
            vals = {}
    if not isinstance(vals, dict):
        vals = {}

    out: Dict[str, Any] = {
        "tipo": tipo,
        "display_name": display_name or tipo,
        "zona": station or "",
        "lat": _as_float(lat),
        "lon": _as_float(lon),
        "conf": confidence,
        "values": vals,
        "detalle": describe_values(tipo, vals),
    }

    lag_h = _as_float(vals.get("calm_duration_h") or vals.get("lag_h") or vals.get("lag_horas"))
    lag_max = None
    t = (tipo or "").upper()

    if conn is not None:
        # Seismic cluster: attach strongest recent epicenter + node
        if out["lat"] is None and ("SEISMIC" in t or "SISMO" in t or "CLUSTER" in t):
            epi = epicentro_reciente(conn, hours=72.0)
            if epi:
                out["lat"] = epi.get("lat")
                out["lon"] = epi.get("lon")
                out["id_nodo"] = epi.get("id_nodo")
                out["nodo_nombre"] = epi.get("nodo_nombre")
                out["region"] = epi.get("region")
                if epi.get("mag") is not None:
                    out["epicentro_mag"] = epi["mag"]
                if epi.get("time_utc"):
                    out["epicentro_time"] = epi["time_utc"]
                if epi.get("dist_km") is not None:
                    out["dist_km"] = epi["dist_km"]
        elif out["lat"] is not None and out["lon"] is not None and not out.get("nodo_nombre"):
            nn = nearest_nodo(conn, out["lat"], out["lon"])
            if nn:
                out["id_nodo"] = nn["id_nodo"]
                out["nodo_nombre"] = nn["nodo_nombre"]
                out["region"] = nn["region"]
                out["dist_km"] = nn["dist_km"]

        # Lag from anticipacion table for seismic-ish classes
        if lag_h is None:
            ec = None
            if "SEISMIC" in t or "CLUSTER" in t:
                ec = "SISMO_M5"
            elif "SCHUMANN" in t:
                ec = "SCHUMANN"
            elif "SILENT" in t:
                lag_h = _as_float(vals.get("calm_duration_h")) or 72.0
            lh, lm = lag_for_event_class(conn, ec) if ec else (None, None)
            if lh is not None:
                lag_h, lag_max = lh, lm

    out["lag_horas"] = lag_h
    out["lag_max_h"] = lag_max

    # Place label
    if out.get("nodo_nombre"):
        lugar = out["nodo_nombre"]
        if out.get("region"):
            lugar = f"{lugar} ({out['region']})"
        if out.get("id_nodo") is not None:
            lugar = f"{lugar} · nodo #{out['id_nodo']}"
        if out.get("dist_km") is not None:
            lugar = f"{lugar} · ~{out['dist_km']} km"
        out["lugar"] = lugar
        out["zona"] = lugar
    elif station and station not in ("regional", "global", ""):
        out["lugar"] = station
        out["zona"] = station
    elif out["lat"] is not None and out["lon"] is not None:
        out["lugar"] = f"{out['lat']:.2f}, {out['lon']:.2f}"
        out["zona"] = out["lugar"]
    else:
        out["lugar"] = station or "ámbito global / sin nodo fijado"
        out["zona"] = out["lugar"]

    return out


def location_block(enriched: Dict[str, Any]) -> str:
    lines = []
    if enriched.get("nodo_nombre") or enriched.get("id_nodo") is not None:
        nom = enriched.get("nodo_nombre") or "sin nombre"
        nid = enriched.get("id_nodo")
        reg = enriched.get("region") or ""
        dist = enriched.get("dist_km")
        bit = f"📍 <b>Nodo alertado:</b> <code>{nom}</code>"
        if nid is not None:
            bit += f" (#{nid})"
        if reg:
            bit += f" — {reg}"
        if dist is not None:
            bit += f" · ~{dist} km del epicentro/ref"
        lines.append(bit)
    elif enriched.get("lugar"):
        lines.append(f"📍 <b>Ubicación:</b> {enriched['lugar']}")
    if enriched.get("lat") is not None and enriched.get("lon") is not None:
        lines.append(
            f"🌐 <b>Coords:</b> <code>{enriched['lat']:.2f}, {enriched['lon']:.2f}</code>"
        )
    if enriched.get("epicentro_mag") is not None:
        et = enriched.get("epicentro_time") or ""
        lines.append(
            f"🌋 <b>Epicentro ref. (ventana):</b> M{float(enriched['epicentro_mag']):.1f}"
            + (f" @ {et}" if et else "")
        )
    return "\n".join(lines)

