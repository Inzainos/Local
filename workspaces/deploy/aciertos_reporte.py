#!/usr/bin/env python3
"""
Extrae los aciertos (ACIERTO en TBL_JUEZ_AUDITORIA) y los formatea para reportes.

Muestra:
- Eventos predichos correctamente
- Fecha de predicción vs fecha real
- Precisión del predictor (cuántos días antes)
- Confianza del bot
- Tasa de aciertos histórica
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional

DB_DEFAULT = str(
    Path(__file__).parent.parent / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db"
)


def _barra(pct: float, ancho: int = 10) -> str:
    """Barra visual ▓▓▓░░ para porcentajes en Markdown."""
    if pct is None:
        return ""
    llenos = round(max(0.0, min(1.0, pct)) * ancho)
    return "▓" * llenos + "░" * (ancho - llenos)


def obtener_aciertos_recientes(db_path: str = DB_DEFAULT, dias: int = 30) -> List[Dict]:
    """
    Obtiene los aciertos (ACIERTO en TBL_JUEZ_AUDITORIA) de los últimos N días.

    Retorna lista de dicts:
    {
        "timestamp_prediccion": <datetime>,
        "timestamp_evento": <datetime>,
        "dias_anticipacion": <int>,
        "bot": <str>,
        "event_class": <str>,
        "magnitude": <float>,
        "location": <str>,
        "confianza": <float>,  # 0-1
        "fase": <str>,
    }
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    hace_n_dias = datetime.now(timezone.utc) - timedelta(days=dias)
    timestamp_cutoff = hace_n_dias.timestamp()

    query = """
    SELECT
        j.timestamp as timestamp_prediccion,
        j.resuelto_at,
        ROUND(j.ventana_h / 24.0, 1) as dias_anticipacion,
        j.bot_name,
        j.prediccion,
        j.confianza,
        j.verdad,
        j.detalles_json,
        j.fase,
        j.resultado
    FROM TBL_JUEZ_AUDITORIA j
    WHERE j.resultado = 'ACIERTO'
      AND j.timestamp >= ?
      AND j.fase = 'viva'
    ORDER BY j.timestamp DESC
    """

    rows = conn.execute(query, (timestamp_cutoff,)).fetchall()
    conn.close()

    import json
    import re

    aciertos = []
    for row in rows:
        event_class = "CALMA" if row["prediccion"] in ("neutral", "no_signal") else row["prediccion"].upper()
        magnitude = None
        location = "zonas monitoreadas"
        ts_evento_dt = None

        if row["detalles_json"]:
            try:
                det = json.loads(row["detalles_json"])
                f_matches = det.get("firma_matches", [])
                if f_matches:
                    m0 = f_matches[0]
                    event_class = m0.get("event_class", event_class)
                    location = m0.get("nodo_nombre", location)
            except Exception:
                pass

        if row["verdad"]:
            m_mag = re.search(r"máx M([0-9.]+)", row["verdad"])
            if m_mag:
                magnitude = float(m_mag.group(1))

        if row["resuelto_at"]:
            try:
                ts_evento_dt = datetime.fromisoformat(row["resuelto_at"].replace("Z", "+00:00"))
            except Exception:
                pass

        aciertos.append({
            "timestamp_prediccion": datetime.fromtimestamp(row["timestamp_prediccion"], tz=timezone.utc),
            "timestamp_evento": ts_evento_dt,
            "dias_anticipacion": row["dias_anticipacion"],
            "bot": row["bot_name"],
            "event_class": event_class,
            "magnitude": magnitude,
            "location": location,
            "confianza": row["confianza"],
            "fase": row["fase"],
        })

    return aciertos


def obtener_estadisticas_aciertos(db_path: str = DB_DEFAULT, dias: int = 90) -> Dict:
    """
    Calcula estadísticas de aciertos:
    - Total aciertos vs fallos vs falsos positivos
    - Tasa de aciertos por bot
    - Precisión promedio (días de anticipación)
    - Confianza promedio
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    hace_n_dias = datetime.now(timezone.utc) - timedelta(days=dias)
    timestamp_cutoff = hace_n_dias.timestamp()

    # Total general
    total_query = """
    SELECT
        SUM(CASE WHEN resultado = 'ACIERTO' THEN 1 ELSE 0 END) as aciertos,
        SUM(CASE WHEN resultado = 'FALLO' THEN 1 ELSE 0 END) as fallos,
        SUM(CASE WHEN resultado = 'FALSO_POSITIVO' THEN 1 ELSE 0 END) as falsos_positivos,
        COUNT(*) as total
    FROM TBL_JUEZ_AUDITORIA
    WHERE timestamp >= ? AND fase = 'viva'
    """

    total_row = conn.execute(total_query, (timestamp_cutoff,)).fetchone()

    # Por bot
    por_bot_query = """
    SELECT
        bot_name,
        SUM(CASE WHEN resultado = 'ACIERTO' THEN 1 ELSE 0 END) as aciertos,
        COUNT(*) as total,
        ROUND(AVG(confianza), 3) as confianza_promedio,
        ROUND(AVG(ventana_h / 24.0), 1) as dias_anticipacion_promedio
    FROM TBL_JUEZ_AUDITORIA
    WHERE timestamp >= ? AND fase = 'viva' AND resultado IN ('ACIERTO', 'FALLO', 'FALSO_POSITIVO')
    GROUP BY bot_name
    ORDER BY aciertos DESC
    """

    por_bot = conn.execute(por_bot_query, (timestamp_cutoff,)).fetchall()

    conn.close()

    por_bot_dict = {}
    for row in por_bot:
        por_bot_dict[row["bot_name"]] = {
            "aciertos": row["aciertos"],
            "total": row["total"],
            "tasa_acierto": row["aciertos"] / row["total"] if row["total"] > 0 else 0,
            "confianza_promedio": row["confianza_promedio"],
            "dias_anticipacion_promedio": row["dias_anticipacion_promedio"],
        }

    return {
        "periodo_dias": dias,
        "aciertos_totales": total_row["aciertos"] or 0,
        "fallos_totales": total_row["fallos"] or 0,
        "falsos_positivos_totales": total_row["falsos_positivos"] or 0,
        "total_predicciones": total_row["total"] or 0,
        "tasa_acierto_global": (total_row["aciertos"] or 0) / (total_row["total"] or 1),
        "por_bot": por_bot_dict,
    }


def seccion_aciertos_markdown(db_path: str = DB_DEFAULT, dias: int = 30) -> str:
    """
    Genera la sección Markdown de aciertos para insertar en reportes.
    """
    aciertos = obtener_aciertos_recientes(db_path, dias)
    stats = obtener_estadisticas_aciertos(db_path, dias)

    lineas = [
        "## ✅ Aciertos y Predicciones Correctas",
        "",
        "> El sistema también tiene victorias que celebrar. Esta sección documenta "
        "cuándo nuestras predicciones fueron correctas: eventos que anticipamos, "
        "qué tan bien los predijimos, y cuántos días antes vimos el patrón.",
        "",
    ]

    # ── Estadísticas generales ──
    total = stats["total_predicciones"]
    aciertos_n = stats["aciertos_totales"]
    tasa = stats["tasa_acierto_global"]

    lineas += [
        "### 📊 Resumen — Últimos {} días".format(dias),
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| **Aciertos** | {aciertos_n} |",
        f"| **Fallos** | {stats['fallos_totales']} |",
        f"| **Falsos positivos** | {stats['falsos_positivos_totales']} |",
        f"| **Tasa de acierto** | {tasa:.1%} `{_barra(tasa, 12)}` |",
        f"| **Total predicciones** | {total} |",
        "",
    ]

    # ── Por bot ──
    if stats["por_bot"]:
        lineas += [
            "### 🤖 Desempeño por Bot",
            "",
            "| Bot | Aciertos | Tasa | Confianza | Anticipación (días) |",
            "|-----|----------|------|-----------|----------------------|",
        ]
        for bot, datos in stats["por_bot"].items():
            tasa_bot = datos["tasa_acierto"]
            conf = datos["confianza_promedio"] or 0
            dias_ant = datos["dias_anticipacion_promedio"] or 0
            lineas.append(
                f"| {bot} | {datos['aciertos']}/{datos['total']} | "
                f"{tasa_bot:.0%} `{_barra(tasa_bot, 8)}` | "
                f"{conf:.2f} | {dias_ant:.1f} |"
            )
        lineas.append("")

    # ── Eventos recientes correctamente predichos ──
    if aciertos:
        lineas += [
            "### 🎯 Eventos Predichos Correctamente (más recientes primero)",
            "",
        ]

        for acierto in aciertos[:10]:  # Mostrar top 10
            ts_pred = acierto["timestamp_prediccion"].strftime("%Y-%m-%d %H:%M")
            ts_evento = acierto["timestamp_evento"].strftime("%Y-%m-%d %H:%M") if acierto["timestamp_evento"] else "—"
            dias_ant = acierto["dias_anticipacion"] or "—"
            magnitude = f"M{acierto['magnitude']:.1f}" if acierto["magnitude"] else "—"
            confianza = acierto["confianza"] or 0
            bot = acierto["bot"]
            event_type = acierto["event_class"] or "—"
            location = acierto["location"] or "—"

            lineas += [
                f"#### {bot.upper()} — {event_type} {magnitude} ({location})",
                "",
                f"- **Predicción:** {ts_pred} UTC",
                f"- **Evento real:** {ts_evento} UTC",
                f"- **Anticipación:** {dias_ant} días",
                f"- **Confianza:** {confianza:.1%} `{_barra(confianza, 10)}`",
                f"- **Fase:** {acierto['fase']}",
                "",
            ]

        if len(aciertos) > 10:
            lineas.append(f"_... y {len(aciertos) - 10} aciertos más en los últimos {dias} días_")
            lineas.append("")
    else:
        lineas += [
            "**Aún no hay aciertos registrados en este período.**",
            "El sistema comenzó hace poco o estamos en fase de aprendizaje.",
            "",
        ]

    return "\n".join(lineas)


if __name__ == "__main__":
    # Para debug: mostrar tabla de aciertos
    print(seccion_aciertos_markdown())
