"""
Sentinel Omega — Generador de Reportes
=======================================
Tres reportes independientes:

  1. reporte_general(db_path)  → resumen global de TODOS los bots (cada 2h).
  2. reporte_padre(db_path)    → análisis profundo solo del Padre (cada 6h).
  3. reporte_omega(db_path)    → análisis profundo solo de Omega (cada 6h).

Ambos bots especializados (Padre y Omega) son independientes entre sí:
  - Padre correlaciona los 6 bots de dominio cruzado.
  - Omega correlaciona su propio dominio completo y se evalúa solo.

Uso:
    from sentinel_omega.infrastructure.pipeline.reporte_sentinel import (
        reporte_general, reporte_padre, reporte_omega,
    )
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers de formato
# ──────────────────────────────────────────────────────────────────────────────

WIDTH = 72


def _sep(char="─", n=WIDTH):
    return char * n


def _title(text, char="═"):
    pad = max(0, WIDTH - len(text) - 4)
    left = pad // 2
    right = pad - left
    return f"{char * (left + 2)}  {text}  {char * (right + 2)}"


def _section(text):
    return f"\n{'▌'} {text.upper()}\n{_sep('╌')}"


def _bar(value: float, max_val: float, width: int = 30, fill="█", empty="░") -> str:
    if max_val <= 0:
        return empty * width
    filled = int(round(value / max_val * width))
    filled = max(0, min(filled, width))
    return fill * filled + empty * (width - filled)


def _pct_bar(pct: float, width: int = 20) -> str:
    return f"{_bar(pct, 1.0, width)} {pct * 100:5.1f}%"


def _tabla(headers: List[str], rows: List[List[Any]], col_min: int = 10) -> str:
    widths = [max(col_min, len(str(h))) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))
    sep = "┼".join("─" * (w + 2) for w in widths)
    sep = f"├{sep}┤"
    header_row = "│".join(f" {str(h):<{w}} " for h, w in zip(headers, widths))
    header_row = f"│{header_row}│"
    top = "┬".join("─" * (w + 2) for w in widths)
    top = f"┌{top}┐"
    bottom = "┴".join("─" * (w + 2) for w in widths)
    bottom = f"└{bottom}┘"
    data_rows = []
    for row in rows:
        cells = []
        for i, w in enumerate(widths):
            cell = str(row[i]) if i < len(row) else ""
            cells.append(f" {cell:<{w}} ")
        data_rows.append(f"│{'│'.join(cells)}│")
    lines = [top, header_row, sep]
    lines.extend(data_rows)
    lines.append(bottom)
    return "\n".join(lines)


def _sparkline(values: List[float], width: int = 20) -> str:
    blocks = " ▁▂▃▄▅▆▇█"
    if not values:
        return "─" * width
    mn, mx = min(values), max(values)
    rng = mx - mn or 1e-9
    sampled = values
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    return "".join(blocks[min(8, int((v - mn) / rng * 8))] for v in sampled)


def _conn(db_path: str) -> sqlite3.Connection:
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    return c


def _safe_query(conn, query, params=()):
    try:
        return conn.execute(query, params).fetchall()
    except sqlite3.OperationalError:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Bloque reutilizable: auditoría Juez para cualquier bot
# ──────────────────────────────────────────────────────────────────────────────

def _bloque_juez_bot(conn, bot_name: str, lines: list) -> dict:
    """Imprime y devuelve las estadísticas del Juez para un bot específico.

    Vara canónica: viva_real (solo fase='viva') — la misma definición que
    generar_reporte.py y reporte_ejecutivo.py. Las filas de entrenamiento
    (reconocimiento/backtest/observacion/trasfondo) jamás puntúan aquí.
    """
    padre_juez = _safe_query(
        conn,
        "SELECT resultado, COUNT(*) as n, COALESCE(SUM(severidad),0) as sev "
        "FROM viva_real WHERE bot_name=? AND resultado != 'PENDIENTE' "
        "GROUP BY resultado",
        (bot_name,)
    )
    juez_dict = {r["resultado"]: {"n": r["n"], "sev": r["sev"]} for r in padre_juez}
    aciertos = juez_dict.get("ACIERTO", {}).get("n", 0)
    fallos = juez_dict.get("FALLO", {}).get("n", 0)
    fps = juez_dict.get("FALSO_POSITIVO", {}).get("n", 0)
    total_j = aciertos + fallos + fps
    asert = aciertos / max(1, total_j)
    sev_total = sum(v["sev"] for v in juez_dict.values())

    lines.append(f"  Aciertos:        {aciertos:>6}")
    lines.append(f"  Fallos:          {fallos:>6}   (severidad total: {sev_total:.1f})")
    lines.append(f"  Falsos positivos:{fps:>6}")
    lines.append(f"  Asertividad:     {_pct_bar(asert, 30)}")

    recientes = _safe_query(
        conn,
        "SELECT resultado FROM viva_real "
        "WHERE bot_name=? AND resultado != 'PENDIENTE' "
        "ORDER BY timestamp DESC LIMIT 200",
        (bot_name,)
    )
    if recientes:
        vals = [1.0 if r["resultado"] == "ACIERTO" else 0.0 for r in reversed(recientes)]
        window = 10
        smoothed = [sum(vals[max(0, i-window):i+1]) / len(vals[max(0, i-window):i+1])
                    for i in range(len(vals))]
        lines.append(f"\n  Tendencia aciertos (últimos {len(vals)} registros):")
        lines.append(f"  {_sparkline(smoothed, width=50)}")
        lines.append(f"  └── tendencia {'↑ MEJORANDO' if smoothed[-1] > smoothed[0] else '↓ AJUSTANDO'}")
    return juez_dict


def _bloque_sesgo_bot(conn, bot_name: str, lines: list) -> dict:
    """Imprime y devuelve el sesgo de un bot específico."""
    sesgo = _safe_query(
        conn,
        "SELECT n, recon_insample, recon_causal, sesgo, castigos "
        "FROM tbl_sesgo_aprendizaje WHERE bot = ?",
        (bot_name,)
    )
    if not sesgo:
        lines.append(f"  Sin datos de sesgo para {bot_name}.")
        return {}
    r = sesgo[0]
    insample = r["recon_insample"]
    causal = r["recon_causal"]
    sesgo_v = r["sesgo"]
    lines.append(f"  Eventos evaluados:         {r['n']}")
    lines.append(f"  Reconocimiento in-sample:  {_pct_bar(insample, 30)}")
    lines.append(f"  Reconocimiento causal:     {_pct_bar(causal, 30)}")
    lines.append(f"  Sesgo (dif):               {sesgo_v * 100:.1f}%")
    lines.append(f"  Castigos aplicados:        {r['castigos']}")
    if sesgo_v < 0.10:
        lines.append(f"  ✓ {bot_name.upper()} SANO: reconoce con memoria anterior.")
    elif sesgo_v < 0.30:
        lines.append(f"  ⚠ {bot_name.upper()} SESGO MODERADO: parte in-sample.")
    else:
        lines.append(f"  ✗ {bot_name.upper()} SESGO ALTO: principalmente in-sample.")
    return dict(r)


# ──────────────────────────────────────────────────────────────────────────────
# REPORTE GENERAL  (todos los bots — cada 2h)
# ──────────────────────────────────────────────────────────────────────────────

def reporte_general(db_path: str) -> Dict:
    """
    Reporte global del sistema Sentinel Omega post-entrenamiento.
    Incluye Padre y Omega en el resumen comparativo.
    Ejecutar cada 2 horas (ver scheduler_reportes.py).
    """
    conn = _conn(db_path)
    lines = []
    data = {}

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(_title(f"SENTINEL OMEGA — REPORTE GENERAL  [{now_str}]"))
    lines.append("")

    # ── 1. Estado de la Base de Datos ────────────────────────────────────────
    lines.append(_section("1. Estado de la Base de Datos"))
    db_size_mb = Path(db_path).stat().st_size / 1_048_576 if Path(db_path).exists() else 0
    table_counts = {}
    for tbl in [
        "TBL_FIRMAS", "TBL_CICLOS", "TBL_DETECCIONES", "TBL_JUEZ_AUDITORIA",
        "TBL_PESOS_BOTS", "tbl_historico_sismico_raw", "tbl_correlaciones_padre",
        "tbl_correlaciones_omega", "tbl_lag_anticipacion", "tbl_sesgo_aprendizaje",
    ]:
        row = _safe_query(conn, f"SELECT COUNT(*) FROM {tbl}")
        table_counts[tbl] = row[0][0] if row else "N/A"
    lines.append(f"  Ruta:      {db_path}")
    lines.append(f"  Tamaño:    {db_size_mb:.1f} MB\n")
    lines.append(_tabla(["Tabla", "Registros"], [[t, str(c)] for t, c in table_counts.items()]))
    data["db"] = {"size_mb": db_size_mb, "tables": table_counts}

    # ── 2. Firmas por Bot y Estado ───────────────────────────────────────────
    lines.append(_section("2. Firmas por Bot y Estado"))
    firma_rows = _safe_query(
        conn,
        "SELECT bot_name, estado, COUNT(*) as n "
        "FROM TBL_FIRMAS GROUP BY bot_name, estado ORDER BY bot_name, estado"
    )
    bots_order = ["alfa1", "alfa2", "beta1", "beta2", "delta", "jupiter", "padre", "omega"]
    estados_order = ["nueva", "observada", "recurrente", "consolidada"]
    pivot: Dict[str, Dict[str, int]] = {b: {e: 0 for e in estados_order} for b in bots_order}
    for row in firma_rows:
        b, e, n = row["bot_name"], row["estado"], row["n"]
        if b in pivot and e in pivot[b]:
            pivot[b][e] = n
    headers = ["Bot", "Nueva", "Observada", "Recurrente", "Consolidada", "Total", "Barra"]
    trows = []
    for b in bots_order:
        d = pivot[b]
        total = sum(d.values())
        cons = d["consolidada"]
        bar = _bar(cons, max(1, total), width=20)
        trows.append([b, d["nueva"], d["observada"], d["recurrente"], cons, total, bar])
    lines.append(_tabla(headers, trows))
    n_total = sum(sum(d.values()) for d in pivot.values())
    n_cons = sum(d["consolidada"] for d in pivot.values())
    lines.append(f"\n  Total firmas: {n_total}  |  Consolidadas: {n_cons}  ({n_cons/max(1,n_total)*100:.1f}%)")
    data["firmas"] = {"total": n_total, "consolidadas": n_cons, "por_bot": dict(pivot)}

    # ── 3. Pesos Disciplinarios ──────────────────────────────────────────────
    lines.append(_section("3. Pesos Disciplinarios (credibilidad)"))
    pesos_rows = _safe_query(conn, "SELECT bot_name, peso FROM TBL_PESOS_BOTS ORDER BY peso DESC")
    if not pesos_rows:
        lines.append("  Sin pesos en TBL_PESOS_BOTS aún.")
    else:
        max_peso = max(r["peso"] for r in pesos_rows) or 1.0
        p_rows = [[r["bot_name"], f"{r['peso']:.4f}", _bar(r["peso"], max_peso, 30)]
                  for r in pesos_rows]
        lines.append(_tabla(["Bot", "Peso", "Barra de credibilidad"], p_rows))
    data["pesos"] = {r["bot_name"]: r["peso"] for r in pesos_rows}

    # ── 4. Auditoría del Juez ────────────────────────────────────────────────
    lines.append(_section("4. Auditoría del Juez — Asertividad por Bot"))
    juez_rows = _safe_query(
        conn,
        "SELECT bot_name, resultado, COUNT(*) as n, COALESCE(SUM(severidad),0) as sev "
        "FROM viva_real WHERE resultado != 'PENDIENTE' "
        "GROUP BY bot_name, resultado ORDER BY bot_name, resultado"
    )
    juez_pivot: Dict[str, Dict] = {}
    for r in juez_rows:
        b = r["bot_name"]
        if b not in juez_pivot:
            juez_pivot[b] = {"ACIERTO": 0, "FALLO": 0, "FALSO_POSITIVO": 0, "sev": 0.0}
        juez_pivot[b][r["resultado"]] = r["n"]
        juez_pivot[b]["sev"] += r["sev"]
    j_rows = []
    for b in bots_order:
        d = juez_pivot.get(b, {"ACIERTO": 0, "FALLO": 0, "FALSO_POSITIVO": 0, "sev": 0.0})
        total = d["ACIERTO"] + d["FALLO"] + d["FALSO_POSITIVO"]
        asert = d["ACIERTO"] / max(1, total)
        j_rows.append([b, d["ACIERTO"], d["FALLO"], d["FALSO_POSITIVO"],
                       f"{asert*100:.1f}%", f"{d['sev']:.1f}", _pct_bar(asert, 20)])
    lines.append(_tabla(["Bot", "Aciertos", "Fallos", "FP", "Asertividad", "Severidad", "Barra"], j_rows))
    data["juez"] = juez_pivot

    # ── 5. Sesgo de Aprendizaje ──────────────────────────────────────────────
    lines.append(_section("5. Sesgo de Aprendizaje — In-Sample vs Causal"))
    sesgo_rows = _safe_query(
        conn, "SELECT bot, n, recon_insample, recon_causal, sesgo, castigos "
              "FROM tbl_sesgo_aprendizaje ORDER BY sesgo DESC"
    )
    if not sesgo_rows:
        lines.append("  Sin datos. Ejecutar barrido_diario().")
    else:
        lines.append(
            "  In-sample = el bot reconoce con lo que se entrenó (favorecido).\n"
            "  Causal    = solo reconoce con memoria anterior al evento (honesto).\n"
            "  Sesgo alto → el bot 'recuerda el futuro'.\n"
        )
        s_rows = []
        for r in sesgo_rows:
            calidad = "✓ SANO" if r["sesgo"] < 0.15 else ("⚠ SOBREFIT" if r["sesgo"] < 0.4 else "✗ CRÍTICO")
            s_rows.append([r["bot"], r["n"], f"{r['recon_insample']*100:.1f}%",
                           f"{r['recon_causal']*100:.1f}%", f"{r['sesgo']*100:.1f}%",
                           r["castigos"], calidad])
        lines.append(_tabla(["Bot", "N", "In-Sample", "Causal", "Sesgo", "Castigos", "Calidad"], s_rows))
    data["sesgo"] = [dict(r) for r in sesgo_rows]

    # ── 6. Lags de Anticipación ──────────────────────────────────────────────
    lines.append(_section("6. Lags de Anticipación por Clase de Evento"))
    lag_rows = _safe_query(
        conn, "SELECT event_class, lag_promedio_h, lag_max_h, lag_min_h, n_eventos "
              "FROM tbl_lag_anticipacion ORDER BY lag_promedio_h DESC"
    )
    if not lag_rows:
        lines.append("  Sin lags calculados.")
    else:
        max_lag = max(r["lag_promedio_h"] for r in lag_rows) or 1
        l_rows = [[r["event_class"], f"{r['lag_promedio_h']/24:.1f}",
                   f"{r['lag_max_h']/24:.1f}", f"{r['lag_min_h']/24:.1f}",
                   r["n_eventos"], _bar(r["lag_promedio_h"], max_lag, 20)]
                  for r in lag_rows]
        lines.append(_tabla(["Clase", "Prom (días)", "Máx (días)", "Mín (días)", "N evts", "Barra"], l_rows))
    data["lags"] = [dict(r) for r in lag_rows]

    # ── 7. Top Patrones Cruzados ─────────────────────────────────────────────
    lines.append(_section("7. Top Patrones Cruzados — Padre y Omega"))
    for tabla, label in [("tbl_correlaciones_padre", "Padre"), ("tbl_correlaciones_omega", "Omega")]:
        lines.append(f"\n  [{label}]")
        corr_rows = _safe_query(
            conn, f"SELECT patron, event_class, n, fuerza FROM {tabla} ORDER BY fuerza DESC LIMIT 10"
        )
        if not corr_rows:
            lines.append(f"  Sin correlaciones de {label} aún.")
        else:
            max_f = max(r["fuerza"] for r in corr_rows) or 1
            c_rows = [[r["patron"], r["event_class"], r["n"],
                       f"{r['fuerza']:.4f}", _bar(r["fuerza"], max_f, 18)]
                      for r in corr_rows]
            lines.append(_tabla(["Patrón", "Clase evento", "N", "Fuerza", "Barra"], c_rows))
    data["correlaciones"] = {"padre": [], "omega": []}

    # ── 8. Últimas Alertas ───────────────────────────────────────────────────
    lines.append(_section("8. Últimas Alertas del Sistema"))
    alert_rows = _safe_query(
        conn,
        "SELECT timestamp, bot_name, prediccion, confianza, detalles_json "
        "FROM TBL_JUEZ_AUDITORIA WHERE prediccion IN ('alert','watch') "
        "ORDER BY timestamp DESC LIMIT 10"
    )
    if not alert_rows:
        lines.append("  Sin alertas recientes.")
    else:
        a_rows = []
        for r in alert_rows:
            ts = datetime.utcfromtimestamp(r["timestamp"]).strftime("%Y-%m-%d %H:%M")
            try:
                d = json.loads(r["detalles_json"])
                detalle = d.get("clase", d.get("nivel", ""))
            except Exception:
                detalle = ""
            a_rows.append([ts, r["bot_name"], r["prediccion"], f"{r['confianza']:.0%}", detalle])
        lines.append(_tabla(["Timestamp", "Bot", "Señal", "Conf", "Detalle"], a_rows))
    data["ultimas_alertas"] = [dict(r) for r in alert_rows]

    # ── 9. Resumen Ejecutivo ──────────────────────────────────────────────────
    lines.append(_section("9. Resumen Ejecutivo"))
    n_ev = (_safe_query(conn, "SELECT COUNT(*) FROM tbl_historico_sismico_raw WHERE sismo_max_mag >= 4.5") or [(0,)])[0][0]
    lines.append(f"  ▸ Eventos M4.5+ en catálogo:   {n_ev}")
    lines.append(f"  ▸ Total firmas registradas:    {n_total}")
    lines.append(f"  ▸ Firmas consolidadas:         {n_cons}  ({n_cons/max(1,n_total)*100:.1f}%)")
    if pesos_rows:
        top = pesos_rows[0]
        lines.append(f"  ▸ Bot más confiable (peso):    {top['bot_name']}  ({top['peso']:.4f})")
    if juez_pivot:
        mejor = max(juez_pivot.items(),
                    key=lambda x: x[1]["ACIERTO"] / max(1, x[1]["ACIERTO"] + x[1]["FALLO"]))
        b, d = mejor
        asert = d["ACIERTO"] / max(1, d["ACIERTO"] + d["FALLO"])
        lines.append(f"  ▸ Mayor asertividad:           {b}  ({asert*100:.1f}%)")
    if lag_rows:
        ml = lag_rows[0]
        lines.append(f"  ▸ Evento con más anticipación: {ml['event_class']}  ({ml['lag_promedio_h']/24:.1f}d prom)")
    lines.append("")
    lines.append(_sep("═"))
    lines.append("")

    # ── Bitácora de salud del sistema (tbl_salud_sistema) ────────────────
    # Tabla huérfana desde el schema v11 self-expanding (nadie la
    # llenaba). Se restaura aquí — el único lugar donde ya se calculan
    # pesos y asertividad para el reporte — en vez de duplicar esa
    # lógica en otro archivo. Documentada originalmente como:
    # "Bitácora por corte: versión, pesos, asertividad viva, deltas."
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS tbl_salud_sistema (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                corte_at TEXT DEFAULT (datetime('now')),
                version TEXT,
                pesos_json TEXT,
                asertividad_viva REAL,
                deltas_json TEXT
            )"""
        )
        asert_aciertos = sum(d["ACIERTO"] for d in juez_pivot.values())
        asert_resueltos = sum(d["ACIERTO"] + d["FALLO"] for d in juez_pivot.values())
        asertividad_viva = asert_aciertos / max(1, asert_resueltos)

        anterior = conn.execute(
            "SELECT pesos_json, asertividad_viva FROM tbl_salud_sistema "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        deltas = {"asertividad_viva": None, "pesos": {}}
        if anterior:
            pesos_prev = json.loads(anterior[0]) if anterior[0] else {}
            asert_prev = anterior[1] if anterior[1] is not None else 0.0
            deltas["asertividad_viva"] = round(asertividad_viva - asert_prev, 4)
            deltas["pesos"] = {
                bot: round(data["pesos"].get(bot, 0.0) - pesos_prev.get(bot, 0.0), 4)
                for bot in data["pesos"]
            }

        try:
            from sentinel_omega.config.sentinel_config import SentinelOmegaConfig
            version = SentinelOmegaConfig().version
        except Exception:
            version = None

        conn.execute(
            "INSERT INTO tbl_salud_sistema (version, pesos_json, asertividad_viva, "
            "deltas_json) VALUES (?, ?, ?, ?)",
            (version, json.dumps(data["pesos"]), asertividad_viva, json.dumps(deltas)),
        )
        conn.commit()
        data["salud_sistema"] = {"version": version, "asertividad_viva": asertividad_viva,
                                  "deltas": deltas}
    except Exception as e:
        logger.warning(f"No se pudo actualizar tbl_salud_sistema: {e}")

    conn.close()
    print("\n".join(lines))
    logger.info(f"Reporte general — {n_total} firmas, {n_cons} consolidadas.")
    return data


# ──────────────────────────────────────────────────────────────────────────────
# REPORTE DEL PADRE  (cada 6h)
# ──────────────────────────────────────────────────────────────────────────────

def reporte_padre(db_path: str) -> Dict:
    """
    Reporte profundo SOLO del Padre: patrones de patrones, correlaciones
    cruzadas, factores de lag, sesgo, historial de predicciones y ranking
    de firmas más fuertes.
    Ejecutar cada 6 horas (ver scheduler_reportes.py).
    """
    conn = _conn(db_path)
    lines = []
    data = {}
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(_title(f"SENTINEL OMEGA — PADRE  [{now_str}]", char="▓"))
    lines.append("  El Padre correlaciona TODOS los dominios simultáneamente.")
    lines.append("  Patrón de patrones: síntesis multi-bot → veredicto final.")
    lines.append("")

    # P1. Firmas del Padre por Clase y Estado
    lines.append(_section("P1. Firmas del Padre — Inventario"))
    padre_firmas = _safe_query(
        conn,
        "SELECT event_class, estado, COUNT(*) as n FROM TBL_FIRMAS "
        "WHERE bot_name = 'padre' GROUP BY event_class, estado ORDER BY event_class, estado"
    )
    pivot2: Dict[str, Dict] = {}
    for r in padre_firmas:
        cl = r["event_class"]
        if cl not in pivot2:
            pivot2[cl] = {"nueva": 0, "observada": 0, "recurrente": 0, "consolidada": 0}
        pivot2[cl][r["estado"]] = r["n"]
    p1_rows = [[cl, d["nueva"], d["observada"], d["recurrente"], d["consolidada"],
                sum(d.values())] for cl, d in sorted(pivot2.items())]
    lines.append(_tabla(["Clase", "Nueva", "Observada", "Recurrente", "Consolidada", "Total"], p1_rows))
    total_padre = sum(sum(d.values()) for d in pivot2.values())
    cons_padre = sum(d["consolidada"] for d in pivot2.values())
    lines.append(f"\n  Total firmas Padre: {total_padre}  |  Consolidadas: {cons_padre}")
    data["firmas_padre"] = pivot2

    # P2. Correlaciones Cruzadas
    lines.append(_section("P2. Correlaciones Cruzadas — Patrones de Patrones"))
    corr_rows = _safe_query(
        conn, "SELECT patron, event_class, n, fuerza FROM tbl_correlaciones_padre ORDER BY n DESC LIMIT 30"
    )
    if not corr_rows:
        lines.append("  Sin correlaciones. Ejecutar construir_correlaciones_padre().")
    else:
        lines.append(
            "  Cada fila = dominios activos simultáneamente antes del evento.\n"
            "  SOLAR+SISMICO = tormenta solar + actividad sísmica previa.\n"
            "  CALMA = período de calma solar que precede el evento.\n"
        )
        patron_resumen: Dict[str, Dict] = {}
        for r in corr_rows:
            p = r["patron"]
            if p not in patron_resumen:
                patron_resumen[p] = {"clases": [], "total_n": 0, "max_fuerza": 0}
            patron_resumen[p]["clases"].append(r["event_class"])
            patron_resumen[p]["total_n"] += r["n"]
            patron_resumen[p]["max_fuerza"] = max(patron_resumen[p]["max_fuerza"], r["fuerza"])
        max_n = max(v["total_n"] for v in patron_resumen.values()) or 1
        p2_rows = []
        for pat, v in sorted(patron_resumen.items(), key=lambda x: -x[1]["total_n"]):
            clases_str = ", ".join(sorted(set(v["clases"]))[:3])
            if len(v["clases"]) > 3:
                clases_str += f" +{len(v['clases'])-3}"
            p2_rows.append([pat, clases_str, v["total_n"], f"{v['max_fuerza']:.4f}",
                            _bar(v["total_n"], max_n, 18)])
        lines.append(_tabla(["Patrón activo", "Tipos evento", "Total N", "Max fuerza", "Barra"], p2_rows))
        lines.append("\n  Detalle patrón → clase:")
        max_f = max(r["fuerza"] for r in corr_rows) or 1
        c_rows = [[r["patron"], r["event_class"], r["n"], f"{r['fuerza']:.4f}",
                   _bar(r["fuerza"], max_f, 16)] for r in corr_rows]
        lines.append(_tabla(["Patrón", "Clase evento", "N observado", "Fuerza", "Barra"], c_rows))
    data["correlaciones"] = [dict(r) for r in corr_rows]

    # P3. Top Firmas Consolidadas
    lines.append(_section("P3. Top Firmas Consolidadas — Mayor Recurrencia"))
    top_firmas = _safe_query(
        conn,
        "SELECT firma_id, event_class, recurrencia, lag_promedio_h, primera_vista, ultima_vista "
        "FROM TBL_FIRMAS WHERE bot_name='padre' AND estado='consolidada' "
        "ORDER BY recurrencia DESC LIMIT 15"
    )
    if not top_firmas:
        lines.append("  Sin firmas consolidadas del Padre aún.")
    else:
        tf_rows = [[r["firma_id"], r["event_class"], r["recurrencia"],
                    f"{r['lag_promedio_h']/24:.1f}" if r["lag_promedio_h"] else "—",
                    str(r["primera_vista"])[:10], str(r["ultima_vista"])[:10]]
                   for r in top_firmas]
        lines.append(_tabla(["ID", "Clase", "Recurrencias", "Lag prom (d)",
                             "Primera vista", "Última vista"], tf_rows))
    data["top_firmas"] = [dict(r) for r in top_firmas]

    # P4. Lags de Anticipación
    lines.append(_section("P4. Ventana de Anticipación — Tiempo de Aviso"))
    lag_rows = _safe_query(
        conn, "SELECT event_class, lag_promedio_h, lag_max_h, lag_min_h, n_eventos "
              "FROM tbl_lag_anticipacion ORDER BY lag_promedio_h DESC"
    )
    if not lag_rows:
        lines.append("  Sin lags calculados.")
    else:
        lines.append("  ¿Con cuántos días de anticipación detectó el Padre la firma?\n"
                     "  Escala: 336h = 14 días (máximo de la ventana de firma).\n")
        max_lag = max(r["lag_promedio_h"] for r in lag_rows) or 1
        for r in lag_rows:
            prom_d = r["lag_promedio_h"] / 24
            bar = _bar(r["lag_promedio_h"], max_lag, 25)
            lines.append(f"  {r['event_class']:<18} {bar}  "
                         f"{prom_d:.1f}d  [{r['lag_min_h']/24:.1f}–{r['lag_max_h']/24:.1f}d]  N={r['n_eventos']}")
    data["lags_padre"] = [dict(r) for r in lag_rows]

    # P5. Factores de Lag
    lines.append(_section("P5. Factores de Lag — Qué Acelera la Detección"))
    factor_rows = _safe_query(
        conn, "SELECT feature, media_rapidas, media_lentas, diferencia_norm "
              "FROM tbl_factores_lag ORDER BY ABS(diferencia_norm) DESC LIMIT 12"
    )
    if not factor_rows:
        lines.append("  Sin análisis. Ejecutar analizar_factores_lag().")
    else:
        lines.append("  dif < 0 → feature acelera detección.  dif > 0 → feature retrasa.\n")
        f_rows = [[r["feature"], f"{r['media_rapidas']:.3f}", f"{r['media_lentas']:.3f}",
                   f"{r['diferencia_norm']:+.3f}",
                   "⬇ acelera" if r["diferencia_norm"] < 0 else "⬆ retrasa"]
                  for r in factor_rows]
        lines.append(_tabla(["Feature", "Media rápidas", "Media lentas", "Dif norm", "Efecto"], f_rows))
    data["factores_lag"] = [dict(r) for r in factor_rows]

    # P6. Sesgo
    lines.append(_section("P6. Sesgo del Padre — Causalidad Real"))
    data["sesgo_padre"] = _bloque_sesgo_bot(conn, "padre", lines)

    # P7. Heatmap Feature × Clase
    lines.append(_section("P7. Heatmap: Feature × Clase de Evento"))
    heat_rows = _safe_query(
        conn, "SELECT event_class, feature, ratio FROM tbl_patrones_correlacion ORDER BY event_class, feature"
    )
    if not heat_rows:
        lines.append("  Sin datos. Ejecutar calcular_correlaciones_evento().")
    else:
        lines.append("  ████ muy elevado  ▓▓▓▓ elevado  ▒▒▒▒ normal  ░░░░ suprimido\n")
        classes = sorted(set(r["event_class"] for r in heat_rows))[:8]
        heat_data: Dict[str, Dict[str, float]] = {}
        for r in heat_rows:
            heat_data.setdefault(r["event_class"], {})[r["feature"]] = r["ratio"]
        features_heat = ["bz_mean", "kp_max", "schumann_mean", "sismo_count_win",
                         "btc_volatilidad", "so2_kt_win", "fase_lunar", "proton_max"]
        lines.append(f"  {'Feature':<24}" + "".join(f"{c[:10]:<8}" for c in classes))
        lines.append("  " + _sep("─", WIDTH - 2))
        for feat in features_heat:
            row_str = f"  {feat:<24}"
            for cl in classes:
                ratio = heat_data.get(cl, {}).get(feat)
                if ratio is None:
                    row_str += "  ·   "
                elif ratio > 1.5:
                    row_str += " ████ "
                elif ratio > 1.2:
                    row_str += " ▓▓▓▓ "
                elif ratio > 1.0:
                    row_str += " ▒▒▒▒ "
                elif ratio > 0.8:
                    row_str += " ░░░░ "
                else:
                    row_str += "  --  "
            lines.append(row_str)
    data["heatmap"] = [dict(r) for r in heat_rows]

    # P8. Juez
    lines.append(_section("P8. Historial del Juez — Solo Padre"))
    data["juez_padre"] = _bloque_juez_bot(conn, "padre", lines)

    # P9. Credibilidad
    lines.append(_section("P9. Reincidencia y Credibilidad del Padre"))
    n_reincid = (_safe_query(conn, "SELECT COUNT(*) FROM TBL_JUEZ_AUDITORIA "
                                   "WHERE bot_name='padre' AND resultado='FALLO'") or [(0,)])[0][0]
    pesos_padre = _safe_query(conn, "SELECT peso FROM TBL_PESOS_BOTS WHERE bot_name='padre'")
    peso_padre = pesos_padre[0]["peso"] if pesos_padre else None
    lines.append(f"  Fallos históricos acumulados:  {n_reincid}")
    if peso_padre is not None:
        health = "✓ ÓPTIMO" if peso_padre > 0.7 else ("⚠ DEGRADADO" if peso_padre > 0.4 else "✗ CRÍTICO")
        lines.append(f"  Peso actual del Padre:         {peso_padre:.4f}")
        lines.append(f"  Barra de credibilidad:         {_pct_bar(peso_padre, 30)}")
        lines.append(f"  Estado:                        {health}")
    lines.append("")
    lines.append(_sep("▓"))
    lines.append("")
    conn.close()
    print("\n".join(lines))
    logger.info("Reporte del Padre generado.")
    return data


# ──────────────────────────────────────────────────────────────────────────────
# REPORTE DE OMEGA  (cada 6h — solo él, evaluado de forma completamente independiente)
# ──────────────────────────────────────────────────────────────────────────────

def reporte_omega(db_path: str) -> Dict:
    """
    Reporte profundo EXCLUSIVO de Omega.

    Omega es un bot autónomo evaluado sin depender de los otros 6 bots:
    su asertividad, firmas, correlaciones y sesgo se calculan solos.
    Esto permite medir hasta dónde llega Omega por sí mismo.

    Tablas propias:
        tbl_correlaciones_omega  — correlaciones cruzadas de Omega
        tbl_sesgo_aprendizaje    — fila bot='omega'
        TBL_FIRMAS               — donde bot_name='omega'
        TBL_JUEZ_AUDITORIA       — donde bot_name='omega'
        TBL_PESOS_BOTS           — donde bot_name='omega'

    Ejecutar cada 6 horas (ver scheduler_reportes.py).
    """
    conn = _conn(db_path)
    lines = []
    data = {}
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(_title(f"SENTINEL OMEGA — OMEGA INDEPENDIENTE  [{now_str}]", char="░"))
    lines.append("  Omega es evaluado SIN depender del resto del sistema.")
    lines.append("  Su asertividad es autónoma: solo su memoria, solo sus firmas.")
    lines.append("")

    # ── O1. Inventario de Firmas de Omega ─────────────────────────────────────
    lines.append(_section("O1. Firmas de Omega — Inventario"))
    omega_firmas = _safe_query(
        conn,
        "SELECT event_class, estado, COUNT(*) as n FROM TBL_FIRMAS "
        "WHERE bot_name = 'omega' GROUP BY event_class, estado ORDER BY event_class, estado"
    )
    pivot_o: Dict[str, Dict] = {}
    for r in omega_firmas:
        cl = r["event_class"]
        if cl not in pivot_o:
            pivot_o[cl] = {"nueva": 0, "observada": 0, "recurrente": 0, "consolidada": 0}
        pivot_o[cl][r["estado"]] = r["n"]
    if not pivot_o:
        lines.append("  Sin firmas de Omega aún. ¿Se corrió entrenamiento?")
    else:
        o1_rows = [[cl, d["nueva"], d["observada"], d["recurrente"], d["consolidada"],
                    sum(d.values())] for cl, d in sorted(pivot_o.items())]
        lines.append(_tabla(["Clase", "Nueva", "Observada", "Recurrente", "Consolidada", "Total"], o1_rows))
    total_omega = sum(sum(d.values()) for d in pivot_o.values())
    cons_omega = sum(d["consolidada"] for d in pivot_o.values())
    lines.append(f"\n  Total firmas Omega: {total_omega}  |  Consolidadas: {cons_omega}  "
                 f"({cons_omega/max(1,total_omega)*100:.1f}%)")
    data["firmas_omega"] = pivot_o

    # ── O2. Top Firmas Consolidadas ──────────────────────────────────────────
    lines.append(_section("O2. Top Firmas Consolidadas — Mayor Recurrencia"))
    top_o = _safe_query(
        conn,
        "SELECT firma_id, event_class, recurrencia, lag_promedio_h, primera_vista, ultima_vista "
        "FROM TBL_FIRMAS WHERE bot_name='omega' AND estado='consolidada' "
        "ORDER BY recurrencia DESC LIMIT 15"
    )
    if not top_o:
        lines.append("  Sin firmas consolidadas de Omega aún.")
    else:
        o2_rows = [[r["firma_id"], r["event_class"], r["recurrencia"],
                    f"{r['lag_promedio_h']/24:.1f}" if r["lag_promedio_h"] else "—",
                    str(r["primera_vista"])[:10], str(r["ultima_vista"])[:10]]
                   for r in top_o]
        lines.append(_tabla(["ID", "Clase", "Recurrencias", "Lag prom (d)",
                             "Primera vista", "Última vista"], o2_rows))
    data["top_firmas"] = [dict(r) for r in top_o]

    # ── O3. Correlaciones Propias de Omega ────────────────────────────────────
    lines.append(_section("O3. Correlaciones de Omega — Patrones Propios"))
    lines.append(
        "  Estas correlaciones se construyen SOLO con la memoria de Omega.\n"
        "  No mezcla información de los otros bots.\n"
        "  Patrón = qué dominios cubrió Omega antes del evento.\n"
    )
    corr_o = _safe_query(
        conn,
        "SELECT patron, event_class, n, fuerza FROM tbl_correlaciones_omega "
        "ORDER BY n DESC LIMIT 30"
    )
    if not corr_o:
        lines.append("  Sin correlaciones de Omega. Ejecutar construir_correlaciones_omega().")
    else:
        patron_o: Dict[str, Dict] = {}
        for r in corr_o:
            p = r["patron"]
            if p not in patron_o:
                patron_o[p] = {"clases": [], "total_n": 0, "max_fuerza": 0.0}
            patron_o[p]["clases"].append(r["event_class"])
            patron_o[p]["total_n"] += r["n"]
            patron_o[p]["max_fuerza"] = max(patron_o[p]["max_fuerza"], r["fuerza"])
        max_n = max(v["total_n"] for v in patron_o.values()) or 1
        o3_resumen = []
        for pat, v in sorted(patron_o.items(), key=lambda x: -x[1]["total_n"]):
            clases_str = ", ".join(sorted(set(v["clases"]))[:3])
            if len(v["clases"]) > 3:
                clases_str += f" +{len(v['clases'])-3}"
            o3_resumen.append([pat, clases_str, v["total_n"],
                               f"{v['max_fuerza']:.4f}", _bar(v["total_n"], max_n, 20)])
        lines.append(_tabla(["Patrón", "Tipos evento", "Total N", "Max fuerza", "Barra"], o3_resumen))
        lines.append("\n  Detalle patrón → clase:")
        max_f = max(r["fuerza"] for r in corr_o) or 1
        o3_det = [[r["patron"], r["event_class"], r["n"],
                   f"{r['fuerza']:.4f}", _bar(r["fuerza"], max_f, 16)]
                  for r in corr_o]
        lines.append(_tabla(["Patrón", "Clase evento", "N observado", "Fuerza", "Barra"], o3_det))
    data["correlaciones_omega"] = [dict(r) for r in corr_o]

    # ── O4. Ventana de Anticipación de Omega ─────────────────────────────────
    lines.append(_section("O4. Ventana de Anticipación — Solo Omega"))
    lag_o = _safe_query(
        conn,
        "SELECT event_class, lag_promedio_h, lag_max_h, lag_min_h, n_eventos "
        "FROM tbl_lag_anticipacion_omega ORDER BY lag_promedio_h DESC"
    )
    if not lag_o:
        # Fallback: tabla general si no hay tabla omega separada
        lag_o = _safe_query(
            conn,
            "SELECT event_class, AVG(lag_promedio_h) as lag_promedio_h, "
            "MAX(lag_max_h) as lag_max_h, MIN(lag_min_h) as lag_min_h, "
            "SUM(n_eventos) as n_eventos FROM tbl_lag_anticipacion GROUP BY event_class "
            "ORDER BY lag_promedio_h DESC"
        )
    if not lag_o:
        lines.append("  Sin lags de Omega calculados.")
    else:
        lines.append("  ¿Con cuántos días avisa Omega por sí solo?\n"
                     "  Si el lag es comparable al del Padre → Omega es autosuficiente.\n")
        max_lag = max(r["lag_promedio_h"] for r in lag_o) or 1
        for r in lag_o:
            prom_d = r["lag_promedio_h"] / 24
            bar = _bar(r["lag_promedio_h"], max_lag, 25)
            lines.append(
                f"  {r['event_class']:<18} {bar}  "
                f"{prom_d:.1f}d  [{r['lag_min_h']/24:.1f}–{r['lag_max_h']/24:.1f}d]  N={r['n_eventos']}"
            )
    data["lags_omega"] = [dict(r) for r in lag_o]

    # ── O5. Sesgo de Omega ───────────────────────────────────────────────────
    lines.append(_section("O5. Sesgo de Omega — Causalidad Real"))
    lines.append(
        "  In-sample = Omega reconoce con la firma con la que se entrenó.\n"
        "  Causal    = Omega reconoce SOLO con memoria anterior al evento.\n"
        "  Un sesgo bajo aquí confirma que Omega aprende patrones reales.\n"
    )
    data["sesgo_omega"] = _bloque_sesgo_bot(conn, "omega", lines)

    # ── O6. Auditoría del Juez — Solo Omega ──────────────────────────────────
    lines.append(_section("O6. Historial del Juez — Solo Omega"))
    lines.append(
        "  Evaluación completamente independiente: el Juez juzga a Omega\n"
        "  sin compararlo contra otros bots ni dependiendo de ellos.\n"
    )
    data["juez_omega"] = _bloque_juez_bot(conn, "omega", lines)

    # ── O7. Credibilidad y Peso de Omega ─────────────────────────────────────
    lines.append(_section("O7. Credibilidad y Peso de Omega"))
    n_fallos = (_safe_query(conn, "SELECT COUNT(*) FROM TBL_JUEZ_AUDITORIA "
                                  "WHERE bot_name='omega' AND resultado='FALLO'") or [(0,)])[0][0]
    pesos_o = _safe_query(conn, "SELECT peso FROM TBL_PESOS_BOTS WHERE bot_name='omega'")
    peso_o = pesos_o[0]["peso"] if pesos_o else None
    lines.append(f"  Fallos históricos acumulados:  {n_fallos}")
    if peso_o is not None:
        health = "✓ ÓPTIMO" if peso_o > 0.7 else ("⚠ DEGRADADO" if peso_o > 0.4 else "✗ CRÍTICO")
        lines.append(f"  Peso actual de Omega:          {peso_o:.4f}")
        lines.append(f"  Barra de credibilidad:         {_pct_bar(peso_o, 30)}")
        lines.append(f"  Estado:                        {health}")
    else:
        lines.append("  Sin peso registrado para Omega en TBL_PESOS_BOTS.")
    data["peso_omega"] = peso_o

    # ── O8. Comparativa Omega vs Sistema Completo ─────────────────────────────
    lines.append(_section("O8. Comparativa — Omega vs Sistema Completo"))
    lines.append(
        "  Compara la asertividad de Omega solo vs la del sistema con todos los bots.\n"
        "  Si Omega individual supera o iguala al sistema → muy alta autonomía.\n"
    )
    # Juez Omega
    jd_o = data.get("juez_omega", {})
    aciertos_o = jd_o.get("ACIERTO", {}).get("n", 0)
    total_o = aciertos_o + jd_o.get("FALLO", {}).get("n", 0) + jd_o.get("FALSO_POSITIVO", {}).get("n", 0)
    asert_o = aciertos_o / max(1, total_o)
    # Juez sistema
    juez_total = _safe_query(
        conn,
        "SELECT resultado, COUNT(*) as n FROM viva_real "
        "WHERE resultado != 'PENDIENTE' GROUP BY resultado"
    )
    jt = {r["resultado"]: r["n"] for r in juez_total}
    aciertos_s = jt.get("ACIERTO", 0)
    total_s = aciertos_s + jt.get("FALLO", 0) + jt.get("FALSO_POSITIVO", 0)
    asert_s = aciertos_s / max(1, total_s)
    comp_rows = [
        ["Omega (solo)",    f"{asert_o*100:.1f}%", str(total_o),   _pct_bar(asert_o, 25)],
        ["Sistema (todos)", f"{asert_s*100:.1f}%", str(total_s), _pct_bar(asert_s, 25)],
    ]
    lines.append(_tabla(["Contexto", "Asertividad", "Total ev.", "Barra"], comp_rows))
    diferencia = (asert_o - asert_s) * 100
    linea = f"  Diferencia Omega−Sistema: {diferencia:+.1f}pp"
    if diferencia >= 0:
        linea += "  → Omega es AUTÓNOMAMENTE COMPETENTE."
    else:
        linea += "  → Omega se beneficia del contexto del sistema."
    lines.append(linea)
    data["comparativa"] = {"asert_omega": asert_o, "asert_sistema": asert_s,
                            "diferencia_pp": round(diferencia, 2)}

    lines.append("")
    lines.append(_sep("░"))
    lines.append("")
    conn.close()
    print("\n".join(lines))
    logger.info("Reporte de Omega generado.")
    return data
