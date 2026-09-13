"""
Verificación del Juez — real vs predicción, cada 2 horas (mismo ritmo del ciclo).

Cada ciclo del Padre (~2 h) registra predicciones; el Juez confronta las
pendientes cuya ventana ya expiró contra el catálogo real (USGS + futuros
multi-evento). Ventana por fila: 2 h mínimo de sesgo continuo, o el lag
típico de la firma/evento si es mayor (no se corta a 72 h fijas).

El ritmo se auto-impone: si la última resolución viva tiene menos de
RITMO_HORAS, la pasada se salta (salvo forzar=True).
"""

import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RITMO_HORAS = 2


def _ultima_resolucion_ts(conn: sqlite3.Connection) -> Optional[float]:
    fila = conn.execute(
        "SELECT MAX(resuelto_at) FROM TBL_JUEZ_AUDITORIA WHERE fase = 'viva'"
    ).fetchone()
    if not fila or not fila[0]:
        return None
    try:
        return datetime.strptime(fila[0], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def verificar_juez(
    conn: sqlite3.Connection,
    forzar: bool = False,
    tracker=None,
) -> Dict[str, Any]:
    """Pasa el Juez: resuelve pendientes vivas contra USGS (verdad por fila).

    forzar=True ignora el ritmo de 2 h (vigilante / prueba manual).
    tracker: AssertivityTracker opcional — se alimenta con los eventos para
    la ganancia de Molchan en vivo.
    """
    from sentinel_omega.core.juez.juez import Juez

    ahora = time.time()
    ultima = _ultima_resolucion_ts(conn)
    if not forzar and ultima and (ahora - ultima) < RITMO_HORAS * 3600:
        faltan = (RITMO_HORAS * 3600 - (ahora - ultima)) / 3600
        logger.info(
            f"Juez: última verificación hace <{RITMO_HORAS}h "
            f"(próxima en ~{faltan:.1f}h) — se respeta el ritmo"
        )
        return {"saltada": True}

    from sentinel_omega.infrastructure.api.usgs import fetch_earthquakes
    eq = fetch_earthquakes(min_magnitude=4.5, days=30)
    if eq is None:
        logger.warning("Juez: USGS sin respuesta — verificación pospuesta")
        return {"saltada": True, "motivo": "usgs_caido"}

    eventos: List[Dict[str, Any]] = []
    for _, ev in eq.iterrows():
        try:
            eventos.append({
                "epoch": ev["time"].timestamp(),
                "lat": ev["latitude"],
                "lon": ev["longitude"],
                "magnitude": ev["magnitude"],
            })
        except (KeyError, AttributeError, TypeError):
            continue

    zonas = [
        (z[0], z[1]) for z in conn.execute(
            "SELECT lat, lon FROM TBL_NODOS_TOPOLOGIA "
            "WHERE tipo = 'real' AND activo = 1").fetchall()
    ]

    juez = Juez(conn)
    resueltos = juez.evaluar_pendientes(
        evento_ocurrido=False,
        eventos=eventos,
        zonas=zonas or None,
        fase="viva",
    )

    try:
        from sentinel_omega.core.firmas.cimatica import retroetiquetar_patrones
        retroetiquetar_patrones(conn, eventos)
    except Exception as e:
        logger.warning(f"Retro-etiquetado cimático falló (non-blocking): {e}")

    conteo: Dict[str, int] = {}
    for r in resueltos:
        conteo[r["resultado"]] = conteo.get(r["resultado"], 0) + 1
    viva = dict(conn.execute(
        "SELECT resultado, COUNT(*) FROM viva_real GROUP BY resultado"
    ).fetchall())
    logger.info(
        f"JUEZ verificó: {len(resueltos)} resueltas {conteo or ''} — "
        f"acumulado viva: {viva}"
    )

    if tracker is not None and eventos and tracker.prediction_count:
        try:
            tracker.ingest_events([
                {"latitude": e["lat"], "longitude": e["lon"],
                 "magnitude": e["magnitude"], "time": e["epoch"]}
                for e in eventos
            ])
            res_a, base_a = tracker.validate_with_baseline()
            logger.info(
                f"Molchan vivo: hit={res_a.hit_rate:.0%} "
                f"base={base_a.base_rate:.0%} ganancia={base_a.gain} — "
                f"{base_a.veredicto}"
            )
        except Exception as e:
            logger.warning(f"Molchan vivo falló (non-blocking): {e}")

    castigos = []
    refuerzos = []
    try:
        from sentinel_omega.core.juez.pesos import castigar, reforzar
        for r in resueltos:
            bot = r["bot_name"]
            res = r["resultado"]
            sev = float(r.get("severidad") or 0)
            es_padre = bot in ("padre", "padre_geo")
            if res == "FALLO":
                gravedad = max(1.0, min(3.0, (sev / 10.0) ** 0.5 if sev else 1.0))
                nuevo = castigar(conn, bot, es_padre=es_padre, gravedad=gravedad)
                castigos.append({"bot": bot, "peso": nuevo, "motivo": "FALLO"})
            elif res == "FALSO_POSITIVO":
                nuevo = castigar(conn, bot, es_padre=es_padre, gravedad=1.0)
                castigos.append({"bot": bot, "peso": nuevo, "motivo": "FALSO_POSITIVO"})
            elif res == "ACIERTO":
                nuevo = reforzar(conn, bot)
                refuerzos.append({"bot": bot, "peso": nuevo})
        if castigos or refuerzos:
            conn.commit()
            logger.info(
                f"Juez disciplina: castigos={len(castigos)} "
                f"refuerzos={len(refuerzos)}"
            )
    except Exception as e:
        logger.warning(f"Disciplina post-Juez falló (non-blocking): {e}")

    return {"saltada": False, "resueltas": len(resueltos),
            "conteo": conteo, "viva": viva,
            "castigos": castigos, "refuerzos": refuerzos}
