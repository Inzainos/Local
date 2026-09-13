"""
Reportes periódicos de Sentinel Omega — comparativo diario, semanal y mensual.

Uso (lo agenda Roy Vigilante):
  python deploy/reporte_periodico.py --comparativo   # 12pm/12am MX: hoy vs ayer
  python deploy/reporte_periodico.py --semanal       # domingo 12:15 MX
  python deploy/reporte_periodico.py --mensual       # fin de mes 12:30 MX

Cada reporte:
  - Se escribe en estado/ (versionado por el vigilante).
  - Genera gráficas PNG (matplotlib, fail-soft si no está) en estado/graficas/.
  - Se encola por correo (tbl_correo_salida) con las gráficas adjuntas.
"""

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from deploy.aciertos_reporte import obtener_estadisticas_aciertos

DB_DEFAULT = str(RAIZ / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db")
DIR_ESTADO = RAIZ / "estado"
DIR_GRAFICAS = DIR_ESTADO / "graficas"

MX_UTC_OFFSET = -6  # CDMX, sin horario de verano desde 2022

# Paleta sobria (una sola familia de azules para magnitud, gris para contexto,
# rojo reservado a lo crítico — nunca arcoíris).
COLOR_SERIE = "#2563a8"
COLOR_CONTEXTO = "#9aa5b1"
COLOR_CRITICO = "#b3261e"


def _ahora_mx() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=MX_UTC_OFFSET)


def _dias_resumen(conn, n_dias: int):
    """Series diarias combinando tbl_resumen_diario (compactado) y TBL_CICLOS
    (días aún no barridos) — lo compactado no se pierde, se resume."""
    desde = (_ahora_mx() - timedelta(days=n_dias)).strftime("%Y-%m-%d")
    filas = {
        d: {"dia": d, "n_ciclos": n, "fantasma_media": fm, "fantasma_max": fx,
            "breaches": b, "alertas": a, "senal": s}
        for d, n, fx, fm, b, a, s in conn.execute(
            "SELECT dia, n_ciclos, fantasma_max, fantasma_media, breaches, "
            "alertas, senal_dominante FROM tbl_resumen_diario "
            "WHERE dia >= ? ORDER BY dia", (desde,))
    }
    for d, n, fm, fx, b, a in conn.execute(
        "SELECT date(timestamp, 'unixepoch'), COUNT(*), AVG(fantasma), "
        "MAX(fantasma), SUM(muro_breach), SUM(alerts_dispatched) "
        "FROM TBL_CICLOS WHERE date(timestamp,'unixepoch') >= ? "
        "GROUP BY 1 ORDER BY 1", (desde,)
    ):
        if d not in filas:
            filas[d] = {"dia": d, "n_ciclos": n, "fantasma_media": fm,
                        "fantasma_max": fx, "breaches": b or 0,
                        "alertas": a or 0, "senal": ""}
    return [filas[d] for d in sorted(filas)]


def _viva_en_rango(conn, desde_ts: float, hasta_ts: float):
    t = dict(conn.execute(
        "SELECT resultado, COUNT(*) FROM viva_real "
        "WHERE resultado != 'PENDIENTE' AND timestamp >= ? AND timestamp < ? "
        "GROUP BY resultado", (desde_ts, hasta_ts)).fetchall())
    tot = sum(t.values())
    return (t.get("ACIERTO", 0) / tot if tot else None), tot


def _grafica_serie(dias, campo, titulo, ylabel, nombre, resalta_max=False):
    """Gráfica de línea sobria: una serie, un color, grid tenue."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    if len(dias) < 2:
        return None
    xs = [d["dia"][5:] for d in dias]          # MM-DD
    ys = [d.get(campo) or 0 for d in dias]

    fig, ax = plt.subplots(figsize=(8, 3.2), dpi=120)
    ax.plot(xs, ys, color=COLOR_SERIE, linewidth=2, marker="o",
            markersize=4, zorder=3)
    if resalta_max and ys:
        i = ys.index(max(ys))
        ax.plot(xs[i], ys[i], "o", color=COLOR_CRITICO, markersize=7,
                zorder=4)
        ax.annotate(f"{ys[i]:.1f}", (xs[i], ys[i]), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8,
                    color=COLOR_CRITICO)
    ax.set_title(titulo, fontsize=11, loc="left")
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(axis="y", color=COLOR_CONTEXTO, alpha=0.25, linewidth=0.7)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    ax.tick_params(labelsize=8)
    if len(xs) > 14:
        ax.set_xticks(xs[:: max(1, len(xs) // 10)])
    fig.tight_layout()
    DIR_GRAFICAS.mkdir(parents=True, exist_ok=True)
    ruta = DIR_GRAFICAS / nombre
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def _delta_txt(hoy, ayer, fmt="{:+.1f}"):
    if hoy is None or ayer is None:
        return "—"
    d = hoy - ayer
    flecha = "▲" if d > 0 else ("▼" if d < 0 else "＝")
    return f"{flecha} {fmt.format(d)}"


def _barra(pct: float, ancho: int = 10) -> str:
    """Barra visual ▓▓▓░░ para porcentajes."""
    if pct is None:
        return ""
    llenos = round(max(0.0, min(1.0, pct)) * ancho)
    return "▓" * llenos + "░" * (ancho - llenos)


def _grafica_aciertos_pastel(stats: dict, nombre: str) -> str:
    """Gráfica de pastel: Aciertos vs Fallos vs Falsos Positivos."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ""

    aciertos = stats["aciertos_totales"] or 0
    fallos = stats["fallos_totales"] or 0
    falsos = stats["falsos_positivos_totales"] or 0

    if aciertos + fallos + falsos == 0:
        return ""

    fig, ax = plt.subplots(figsize=(7, 5), dpi=120)
    sizes = [aciertos, fallos, falsos]
    labels = [f"Aciertos\n{aciertos}", f"Fallos\n{fallos}", f"Falsos positivos\n{falsos}"]
    colors = ["#059669", "#dc2626", "#f59e0b"]  # verde, rojo, ámbar

    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, textprops={"fontsize": 9, "weight": "bold"}
    )
    for autotext in autotexts:
        autotext.set_color("white")
        autotext.set_fontsize(8)

    ax.set_title("Distribución de Veredictos", fontsize=11, weight="bold", pad=20)
    fig.tight_layout()
    DIR_GRAFICAS.mkdir(parents=True, exist_ok=True)
    ruta = DIR_GRAFICAS / nombre
    fig.savefig(ruta)
    plt.close(fig)
    return str(ruta)


def _grafica_aciertos_barras(stats: dict, nombre: str) -> str:
    """Gráfica de barras: Tasa de acierto por bot."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ""

    if not stats.get("por_bot"):
        return ""

    bots = list(stats["por_bot"].keys())
    tasas = [stats["por_bot"][bot]["tasa_acierto"] * 100 for bot in bots]

    fig, ax = plt.subplots(figsize=(8, 4), dpi=120)
    bars = ax.barh(bots, tasas, color=COLOR_SERIE, height=0.6)

    # Anotar porcentajes
    for i, (bar, tasa) in enumerate(zip(bars, tasas)):
        ax.text(tasa + 1, bar.get_y() + bar.get_height() / 2,
                f"{tasa:.0f}%", va="center", fontsize=9, weight="bold")

    ax.set_xlabel("Tasa de acierto (%)", fontsize=9)
    ax.set_title("Desempeño por Bot", fontsize=11, weight="bold")
    ax.set_xlim(0, 110)
    ax.grid(axis="x", color=COLOR_CONTEXTO, alpha=0.3, linewidth=0.7)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)

    fig.tight_layout()
    DIR_GRAFICAS.mkdir(parents=True, exist_ok=True)
    ruta = DIR_GRAFICAS / nombre
    fig.savefig(ruta)
    plt.close(fig)
    return str(ruta)


def _seccion_aciertos(db_path: str, dias: int, titulo: str) -> tuple:
    """Genera sección de aciertos con gráficas para reportes periódicos.

    Retorna: (markdown_text, list_of_image_paths)
    """
    try:
        stats = obtener_estadisticas_aciertos(db_path, dias)
    except Exception:
        return "", []

    if stats["total_predicciones"] == 0:
        return f"## ✅ {titulo}\n\n**No hay predicciones auditadas en este período.**\n", []

    imagenes = []
    lineas = [
        f"## ✅ {titulo}",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| **Aciertos** | {stats['aciertos_totales']} |",
        f"| **Fallos** | {stats['fallos_totales']} |",
        f"| **Falsos positivos** | {stats['falsos_positivos_totales']} |",
        f"| **Tasa de acierto** | {stats['tasa_acierto_global']:.1%} `{_barra(stats['tasa_acierto_global'], 12)}` |",
        f"| **Total predicciones** | {stats['total_predicciones']} |",
        "",
    ]

    # Gráfica de pastel
    sufijo = f"aciertos_{dias}d_pastel.png"
    grafica_pastel = _grafica_aciertos_pastel(stats, sufijo)
    if grafica_pastel:
        imagenes.append(grafica_pastel)
        lineas.append(f"![Distribución de veredictos](graficas/{sufijo})")
        lineas.append("")

    if stats["por_bot"]:
        lineas += [
            "### 🤖 Desempeño por Bot",
            "",
            "| Bot | Aciertos | Tasa | Confianza | Anticipación |",
            "|-----|----------|------|-----------|---------------|",
        ]
        for bot, datos in stats["por_bot"].items():
            tasa_bot = datos["tasa_acierto"]
            conf = datos["confianza_promedio"] or 0
            dias_ant = datos["dias_anticipacion_promedio"] or 0
            lineas.append(
                f"| {bot} | {datos['aciertos']}/{datos['total']} | "
                f"{tasa_bot:.0%} `{_barra(tasa_bot, 8)}` | "
                f"{conf:.2f} | {dias_ant:.1f}d |"
            )
        lineas.append("")

        # Gráfica de barras
        sufijo_barras = f"aciertos_{dias}d_barras.png"
        grafica_barras = _grafica_aciertos_barras(stats, sufijo_barras)
        if grafica_barras:
            imagenes.append(grafica_barras)
            lineas.append(f"![Desempeño por bot](graficas/{sufijo_barras})")
            lineas.append("")

    return "\n".join(lineas), imagenes


def comparativo(conn) -> tuple:
    """Hoy vs ayer (corre 12pm y 12am hora MX)."""
    ahora = _ahora_mx()
    dias = _dias_resumen(conn, 3)
    hoy_str = ahora.strftime("%Y-%m-%d")
    ayer_str = (ahora - timedelta(days=1)).strftime("%Y-%m-%d")
    hoy = next((d for d in dias if d["dia"] == hoy_str), None)
    ayer = next((d for d in dias if d["dia"] == ayer_str), None)

    ts_hoy0 = datetime(ahora.year, ahora.month, ahora.day,
                       tzinfo=timezone.utc).timestamp() - MX_UTC_OFFSET * 3600
    viva_hoy, n_hoy = _viva_en_rango(conn, ts_hoy0, ts_hoy0 + 86400)
    viva_ayer, n_ayer = _viva_en_rango(conn, ts_hoy0 - 86400, ts_hoy0)

    cim = conn.execute(
        "SELECT COUNT(*), SUM(primera_vez >= datetime('now','-1 day')) "
        "FROM tbl_cimatica_patrones").fetchone()

    def _v(d, k):
        return d.get(k) if d else None

    lineas = [
        f"# 🔄 Comparativo diario — {hoy_str} vs {ayer_str}",
        f"*Corte {ahora.strftime('%H:%M')} hora MX*", "",
        "| Métrica | Hoy | Ayer | Cambio |",
        "|---|---:|---:|---:|",
        f"| Fantasma medio | {(_v(hoy,'fantasma_media') or 0):.1f} | "
        f"{(_v(ayer,'fantasma_media') or 0):.1f} | "
        f"{_delta_txt(_v(hoy,'fantasma_media'), _v(ayer,'fantasma_media'))} |",
        f"| Fantasma máx | {(_v(hoy,'fantasma_max') or 0):.1f} | "
        f"{(_v(ayer,'fantasma_max') or 0):.1f} | "
        f"{_delta_txt(_v(hoy,'fantasma_max'), _v(ayer,'fantasma_max'))} |",
        f"| Ciclos corridos | {_v(hoy,'n_ciclos') or 0} | "
        f"{_v(ayer,'n_ciclos') or 0} | "
        f"{_delta_txt(_v(hoy,'n_ciclos'), _v(ayer,'n_ciclos'), '{:+.0f}')} |",
        f"| Breaches del Muro | {_v(hoy,'breaches') or 0} | "
        f"{_v(ayer,'breaches') or 0} | "
        f"{_delta_txt(_v(hoy,'breaches'), _v(ayer,'breaches'), '{:+.0f}')} |",
        f"| Asertividad viva (resuelta en el día) | "
        f"{f'{viva_hoy:.0%} (n={n_hoy})' if viva_hoy is not None else '—'} | "
        f"{f'{viva_ayer:.0%} (n={n_ayer})' if viva_ayer is not None else '—'} | "
        f"{_delta_txt(viva_hoy, viva_ayer, '{:+.0%}') if None not in (viva_hoy, viva_ayer) else '—'} |",
        f"| Patrones cimáticos (total / nuevos 24h) | "
        f"{cim[0]} | — | +{cim[1] or 0} |",
        "",
    ]

    aciertos_sec, aciertos_imgs = _seccion_aciertos(DB_DEFAULT, 1, "Aciertos — Últimas 24 horas")
    if aciertos_sec:
        lineas.append(aciertos_sec)

    grafica = _grafica_serie(
        _dias_resumen(conn, 7), "fantasma_media",
        "Fantasma medio — últimos 7 días", "índice fantasma",
        "comparativo_fantasma.png", resalta_max=True)
    if grafica:
        lineas.append("![Fantasma 7 días](graficas/comparativo_fantasma.png)")
    ruta = DIR_ESTADO / "REPORTE_COMPARATIVO.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")

    adjuntos = [str(grafica)] if grafica else []
    adjuntos.extend(aciertos_imgs)
    return ruta, lineas, adjuntos


def _resumen_rango(conn, n_dias, titulo, archivo, prefijo_grafica):
    ahora = _ahora_mx()
    dias = _dias_resumen(conn, n_dias)
    ahora_ts = datetime.now(timezone.utc).timestamp()
    viva, n_viva = _viva_en_rango(conn, ahora_ts - n_dias * 86400, ahora_ts)

    cim = conn.execute(
        "SELECT ambito, COUNT(*), MAX(frecuencia) FROM tbl_cimatica_patrones "
        "GROUP BY ambito").fetchall()
    consistentes = conn.execute(
        "SELECT patron_id, ambito, id_nodo, event_class, frecuencia "
        "FROM tbl_cimatica_patrones WHERE frecuencia >= 3 "
        "ORDER BY frecuencia DESC LIMIT 10").fetchall()

    tot_ciclos = sum(d["n_ciclos"] or 0 for d in dias)
    tot_breach = sum(d["breaches"] or 0 for d in dias)
    fant = [d["fantasma_media"] for d in dias if d["fantasma_media"]]

    lineas = [
        f"# {titulo}",
        f"*Generado {ahora.strftime('%Y-%m-%d %H:%M')} hora MX — "
        f"ventana {n_dias} días*", "",
        "## Resumen",
        f"- Ciclos corridos: **{tot_ciclos}**",
        f"- Fantasma medio del periodo: "
        f"**{(sum(fant)/len(fant)):.1f}**" if fant else
        "- Fantasma medio del periodo: —",
        f"- Fantasma máximo: "
        f"**{max((d['fantasma_max'] or 0) for d in dias):.1f}**"
        if dias else "- Fantasma máximo: —",
        f"- Breaches del Muro: **{tot_breach}**",
        f"- Asertividad viva del periodo: "
        f"**{f'{viva:.0%}' if viva is not None else '—'}** "
        f"(n={n_viva} resueltas)",
        "",
        "## Cimática",
    ]
    for ambito, n, fmax in cim:
        lineas.append(f"- Patrones `{ambito}`: {n} (frecuencia máx {fmax})")
    if consistentes:
        lineas += ["", "| Patrón | Ámbito | Evento asociado | Frecuencia |",
                   "|---|---|---|---:|"]
        for pid, amb, nodo, ec, frec in consistentes:
            lugar = f"nodo {nodo}" if nodo else "general"
            lineas.append(f"| {pid} | {lugar} | {ec or '—'} | {frec} |")
    lineas.append("")

    aciertos_titulo = f"Aciertos — Últimos {n_dias} días"
    aciertos_sec, aciertos_imgs = _seccion_aciertos(DB_DEFAULT, n_dias, aciertos_titulo)
    if aciertos_sec:
        lineas.append(aciertos_sec)

    adjuntos = list(aciertos_imgs)
    for campo, tit, ylab, nombre, resalta in (
        ("fantasma_media", "Fantasma medio diario", "índice",
         f"{prefijo_grafica}_fantasma.png", True),
        ("alertas", "Alertas por día", "alertas",
         f"{prefijo_grafica}_alertas.png", False),
        ("breaches", "Breaches del Muro por día", "breaches",
         f"{prefijo_grafica}_breaches.png", False),
    ):
        g = _grafica_serie(dias, campo, tit, ylab, nombre, resalta_max=resalta)
        if g:
            adjuntos.append(str(g))
            lineas.append(f"![{tit}](graficas/{nombre})")
    ruta = DIR_ESTADO / archivo
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta, lineas, adjuntos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comparativo", action="store_true")
    ap.add_argument("--semanal", action="store_true")
    ap.add_argument("--mensual", action="store_true")
    ap.add_argument("--db", default=DB_DEFAULT)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    from sentinel_omega.infrastructure.api.correo import encolar_correo
    ahora = _ahora_mx().strftime("%Y-%m-%d %H:%M")

    if args.comparativo:
        ruta, lineas, adj = comparativo(conn)
        encolar_correo(conn, f"🔄 Sentinel Omega — comparativo diario {ahora} MX",
                       "\n".join(lineas), tipo="REPORTE", adjuntos=adj)
    elif args.semanal:
        ruta, lineas, adj = _resumen_rango(
            conn, 7, "📅 Reporte semanal — Sentinel Omega",
            "REPORTE_SEMANAL.md", "semanal")
        encolar_correo(conn, f"📅 Sentinel Omega — reporte semanal {ahora} MX",
                       "\n".join(lineas), tipo="REPORTE", adjuntos=adj)
    elif args.mensual:
        ruta, lineas, adj = _resumen_rango(
            conn, 31, "🗓️ Reporte mensual — Sentinel Omega",
            "REPORTE_MENSUAL.md", "mensual")
        encolar_correo(conn, f"🗓️ Sentinel Omega — reporte mensual {ahora} MX",
                       "\n".join(lineas), tipo="REPORTE", adjuntos=adj)
    else:
        ap.error("indica --comparativo, --semanal o --mensual")
    print(f"Reporte generado: {ruta}")


if __name__ == "__main__":
    main()
