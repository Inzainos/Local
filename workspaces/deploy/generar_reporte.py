#!/usr/bin/env python3
"""
Genera estado/REPORTE.md desde la base de datos — los "ojos" del sistema.

Lo usa el vigilante de GitHub Actions después de cada ciclo, y se puede
correr a mano. Sin argumentos usa la DB por defecto.

El reporte está escrito para que cualquier persona lo entienda sin haber
visto el sistema antes: cada sección lleva una explicación en lenguaje
llano y barras visuales donde ayuda.
"""

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Importar módulo de aciertos
sys.path.insert(0, str(Path(__file__).parent))
from aciertos_reporte import seccion_aciertos_markdown

DB_DEFAULT = str(
    Path(__file__).parent.parent / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db"
)
OUT_DEFAULT = str(Path(__file__).parent.parent / "estado" / "REPORTE.md")

# Traducción de variables técnicas a lenguaje llano (para la sección de factores)
NOMBRES_LLANOS = {
    "bz_min": "Campo magnético solar (Bz mínimo)",
    "bz_mean": "Campo magnético solar (Bz promedio)",
    "bz_mean_72h": "Campo magnético solar (Bz, últimas 72h)",
    "viento_max": "Velocidad máxima del viento solar",
    "viento_avg": "Velocidad promedio del viento solar",
    "kp_max": "Índice Kp máximo (tormenta geomagnética)",
    "kp_mean": "Índice Kp promedio",
    "kp_max_72h": "Tormenta geomagnética en las últimas 72h",
    "proton_max": "Lluvia de protones solares (máx)",
    "sismo_count_win": "Sismos en la ventana de 14 días",
    "sismo_count_72h": "Sismos en las últimas 72h",
    "sismo_max_mag_win": "Magnitud sísmica máxima en la ventana",
    "lod_mean": "Duración del día (rotación terrestre)",
    "fase_lunar": "Fase lunar",
    "dist_lunar": "Distancia a la Luna",
    "schumann_hz": "Resonancia Schumann (latido de la Tierra)",
    "schumann_wpc": "Perturbación Schumann",
    "btc_volatilidad": "Volatilidad de Bitcoin (nerviosismo del mercado)",
    "btc_vol_max": "Pico de volatilidad de Bitcoin",
    "btc_ret_win": "Rendimiento de Bitcoin en la ventana",
    "btc_vol_72h": "Volatilidad de Bitcoin (72h)",
    "so2_kt_win": "Gas volcánico SO₂ en la ventana (kilotones)",
    "erupciones_win": "Erupciones registradas en la ventana",
    "so2_kt_90d": "Gas volcánico SO₂ (90 días)",
    "erupciones_90d": "Erupciones (90 días)",
    "delta_cross_coupling": "Acoplamiento geofísico-financiero cruzado",
    "delta_geo_coupling": "Acoplamiento campo magnético-mercado",
    "delta_schumann_coupling": "Acoplamiento Schumann-mercado",
}


def _barra(pct: float, ancho: int = 10) -> str:
    """Barra visual ▓▓▓░░ para porcentajes en Markdown."""
    if pct is None:
        return ""
    llenos = round(max(0.0, min(1.0, pct)) * ancho)
    return "▓" * llenos + "░" * (ancho - llenos)


def generar(db_path: str = DB_DEFAULT, out_path: str = OUT_DEFAULT) -> str:
    conn = sqlite3.connect(db_path)
    ahora = datetime.now(timezone.utc)
    lineas = [
        "# 🌍 Sentinel Omega — Estado del Sistema",
        "",
        f"**Generado:** {ahora.strftime('%Y-%m-%d %H:%M')} UTC "
        f"({(ahora.hour - 6) % 24:02d}:{ahora.minute:02d} UTC-6)",
        "",
        "> **¿Qué es esto?** Sentinel Omega es un sistema que vigila señales "
        "físicas del planeta (campo magnético solar, resonancia de la Tierra, "
        "actividad sísmica, gases volcánicos, incluso el nerviosismo de los "
        "mercados) buscando *precursores*: condiciones que en 32 años de "
        "historia han aparecido **antes** de eventos naturales fuertes. "
        "No predice con certeza — reconoce parecidos con el pasado y avisa "
        "cuando el presente se parece demasiado a los días previos a un "
        "evento. Este reporte es una foto de lo que el sistema ve ahora.",
        "",
    ]

    # ── Último ciclo ──
    ciclo = conn.execute(
        "SELECT timestamp, geo_signal, geo_confidence, fantasma, nivel_riesgo, "
        "precursors_count, precursor_types, muro_walls_active, muro_breach "
        "FROM TBL_CICLOS ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if ciclo:
        ts = datetime.fromtimestamp(ciclo[0], tz=timezone.utc)
        emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}.get(
            ciclo[4], "⚪"
        )
        # Escala visual del fantasma: CRITICAL arranca en 30
        fant_pct = min(1.0, ciclo[3] / 60.0)
        lineas += [
            "## 📡 Último ciclo — lo que el sistema midió hace un momento",
            "",
            "> El **Fantasma** es el termómetro principal: combina en un solo "
            "número la agitación del campo magnético, el viento solar y la "
            "resonancia de la Tierra. Verde 🟢 <5 = calma · Amarillo 🟡 5-15 · "
            "Naranja 🟠 15-30 · Rojo 🔴 ≥30 = condiciones muy cargadas. "
            "El **Muro de los 5** son cinco frentes de vigilancia "
            "(tierra, atmósfera, océano, sol, mercados); si 3 o más se activan "
            "a la vez, distintos dominios físicos están alterados al mismo "
            "tiempo — eso casi nunca es coincidencia.",
            "",
            f"| Métrica | Valor | Lectura |",
            f"|---|---|---|",
            f"| Fantasma | {emoji} **{ciclo[3]:.1f}** `{_barra(fant_pct)}` | "
            f"{ {'LOW': 'calma', 'MODERATE': 'actividad moderada', 'HIGH': 'actividad alta', 'CRITICAL': 'condiciones muy cargadas'}.get(ciclo[4], ciclo[4]) } |",
            f"| Consenso de los 6 bots | {ciclo[1].upper()} ({ciclo[2]:.0%}) | "
            f"{'los bots coinciden en que hay señal' if ciclo[1].upper() == 'ALERT' else 'sin acuerdo suficiente para alertar' if ciclo[1].upper() in ('WATCH', 'NORMAL') else 'evaluando'} |",
            f"| Muro de los 5 frentes | {ciclo[7]}/5 activos | "
            f"{'🚨 **BREACH** — varios dominios alterados a la vez' if ciclo[8] else 'estable — sin convergencia crítica'} |",
            f"| Precursores detectados | {ciclo[5]} | {ciclo[6] or '—'} |",
            f"| Hora de la medición | {ts.strftime('%Y-%m-%d %H:%M')} UTC | |",
            "",
        ]

    # ── 🚦 Semáforo: reglas duras de nivel de riesgo ──
    # Con los números del bloque principal cualquier lector infiere el nivel
    # sin interpretación subjetiva. Mismos umbrales que el reporte ejecutivo.
    mejor_sim = None
    try:
        _m = conn.execute(
            "SELECT detalles_json FROM TBL_JUEZ_AUDITORIA "
            "WHERE bot_name='padre' AND detalles_json LIKE '%firma_matches%' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if _m:
            _fm = json.loads(_m[0]).get("firma_matches", [])
            mejor_sim = max((x.get("similitud", 0) for x in _fm), default=None)
    except sqlite3.OperationalError:
        pass
    if ciclo:
        f_, m_, b_ = ciclo[3] or 0, ciclo[7] or 0, bool(ciclo[8])
        s_ = mejor_sim or 0
        if b_ and f_ >= 30:
            nivel_sem = "🔴 ROJO"
        elif b_ or (f_ >= 15 and s_ >= 0.85):
            nivel_sem = "🟠 NARANJA"
        elif f_ >= 5 or s_ >= 0.80:
            nivel_sem = "🟡 AMARILLO"
        elif f_ > 0 or m_ > 0:
            nivel_sem = "🔵 AZUL"
        else:
            nivel_sem = "🟢 VERDE"
        lineas += [
            "## 🚦 Semáforo — reglas fijas del nivel de riesgo",
            "",
            "> Estas reglas son **cuantitativas y fijas** (revisables por "
            "versión, no por ciclo): con los números de arriba cualquiera "
            "puede inferir el nivel sin interpretación subjetiva. La fila "
            "marcada ➡ es la que dispara hoy.",
            "",
            "| Nivel | Regla (se evalúa de abajo hacia arriba) | Acción interna |",
            "|---|---|---|",
        ]
        filas_sem = [
            ("🔴 ROJO", "Muro ≥3/5 (breach) **y** Fantasma ≥30", "Escalamiento interno"),
            ("🟠 NARANJA", "Muro ≥3/5 (breach) **o** (Fantasma ≥15 y firma ≥85%)", "Revisión manual inmediata"),
            ("🟡 AMARILLO", "Fantasma 5–15 **o** firma ≥80%", "Vigilancia reforzada"),
            ("🔵 AZUL", "Fantasma <5 con detecciones o muros 1–2", "Seguimiento ampliado"),
            ("🟢 VERDE", "Fantasma <5, muro 0/5, sin firmas ≥80%", "Monitoreo base"),
        ]
        for nombre, regla, accion in filas_sem:
            marca = "➡ " if nombre == nivel_sem else ""
            lineas.append(f"| {marca}{nombre} | {regla} | {accion} |")
        lineas += [
            "",
            f"**Nivel del corte: {nivel_sem}** — con Fantasma {f_:.1f}, "
            f"muro {m_}/5{' (breach)' if b_ else ''} y firma máxima "
            f"{f'{s_:.0%}' if mejor_sim else '—'}.",
            "",
        ]

    # ── 📈 Operación reciente: hoy vs cómo solía estar ──
    # No solo la foto: la posición contra las últimas semanas del propio
    # sistema en vivo (medias 7/30 días + percentil).
    try:
        ahora_ts = ahora.timestamp()
        c7 = conn.execute(
            "SELECT fantasma, muro_walls_active, precursor_types "
            "FROM TBL_CICLOS WHERE timestamp >= ?", (ahora_ts - 7 * 86400,)
        ).fetchall()
        c30 = conn.execute(
            "SELECT fantasma, muro_walls_active, precursor_types "
            "FROM TBL_CICLOS WHERE timestamp >= ?", (ahora_ts - 30 * 86400,)
        ).fetchall()
        # Días viejos ya compactados por el barrido → usar el resumen diario
        d30 = conn.execute(
            "SELECT fantasma_media, fantasma_max FROM tbl_resumen_diario "
            "WHERE dia >= date('now', '-30 days')"
        ).fetchall()

        f7 = [r[0] for r in c7 if r[0] is not None]
        f30 = ([r[0] for r in c30 if r[0] is not None]
               + [r[0] for r in d30 if r[0] is not None])
        fmax30 = ([r[0] for r in c30 if r[0] is not None]
                  + [r[1] for r in d30 if r[1] is not None])
        m7 = [r[1] for r in c7 if r[1] is not None]
        m30 = [r[1] for r in c30 if r[1] is not None]
        st7 = [1 if (r[2] and "SILENT" in r[2]) else 0 for r in c7]
        st30 = [1 if (r[2] and "SILENT" in r[2]) else 0 for r in c30]

        def _prom(xs, dec=1):
            return f"{sum(xs)/len(xs):.{dec}f}" if xs else "—"

        def _pctl(v, serie):
            serie = [s for s in serie if s is not None]
            if v is None or not serie:
                return "—"
            return f"P{round(100 * sum(1 for s in serie if s <= v) / len(serie))}"

        # Asertividad viva acumulada y de 7 días — vara canónica: viva_real
        viva_q = (
            "SELECT resultado, COUNT(*) FROM viva_real "
            "WHERE resultado != 'PENDIENTE' {extra} "
            "GROUP BY resultado")

        def _viva(extra="", params=()):
            t = dict(conn.execute(viva_q.format(extra=extra), params).fetchall())
            tot = sum(t.values())
            return (t.get("ACIERTO", 0) / tot) if tot else None

        viva_total = _viva()
        viva_7d = _viva("AND timestamp >= ?", (ahora_ts - 7 * 86400,))

        if ciclo and (f7 or f30):
            f_act = ciclo[3]
            st_act = 1 if (ciclo[6] and "SILENT" in ciclo[6]) else 0
            lineas += [
                "## 📈 Operación reciente — hoy vs cómo solía estar",
                "",
                "> La foto de arriba, puesta en contexto: ¿este corte está "
                "por encima, en el promedio o por debajo de la actividad "
                "usual de las últimas semanas? El **percentil** dice qué "
                "fracción de los cortes recientes fue igual o menor que hoy "
                "(P75 = hoy es más alto que el 75% del último mes).",
                "",
                "| Métrica | Actual | Prom. 7d | Prom. 30d | Máx 30d | Percentil |",
                "|---|---:|---:|---:|---:|---:|",
                f"| Fantasma | {f_act:.1f} | {_prom(f7)} | {_prom(f30)} | "
                f"{max(fmax30):.1f} | {_pctl(f_act, f30)} |"
                if fmax30 else
                f"| Fantasma | {f_act:.1f} | {_prom(f7)} | — | — | — |",
                f"| Muro de los 5 | {ciclo[7]} | {_prom(m7)} | {_prom(m30)} | "
                f"{max(m30) if m30 else '—'} | {_pctl(ciclo[7], m30)} |",
                f"| Silent Trigger | {'activo' if st_act else 'inactivo'} | "
                f"{_prom([x*100 for x in st7], 0)}% ciclos | "
                f"{_prom([x*100 for x in st30], 0)}% ciclos | — | — |",
                f"| Asertividad viva | "
                f"{f'{viva_total:.0%}' if viva_total is not None else '—'} | "
                f"{f'{viva_7d:.0%}' if viva_7d is not None else '—'} | — | — | — |",
                "",
                "*Los promedios de 30 días combinan los ciclos conservados y "
                "el resumen diario del barrido (lo compactado no se pierde, "
                "se resume).*",
                "",
            ]
    except sqlite3.OperationalError:
        pass

    # ── Ganancia sobre el modelo nulo (línea base de Molchan) ──
    try:
        filas_nulo = conn.execute(
            "SELECT verdad, resultado FROM viva_real "
            "WHERE resultado != 'PENDIENTE' AND verdad != ''"
        ).fetchall()
        if filas_nulo:
            total_n = len(filas_nulo)
            con_evento = sum(
                1 for v, _ in filas_nulo if not v.startswith("sin eventos")
            )
            aciertos_n = sum(1 for _, r in filas_nulo if r == "ACIERTO")
            base = con_evento / total_n
            viva_n = aciertos_n / total_n
            ganancia = (viva_n / base) if base > 0 else None
            if ganancia is None:
                veredicto = "sin eventos en las ventanas — ganancia indefinida"
            elif ganancia > 1.5:
                veredicto = "✅ GANANCIA REAL: el sistema aporta información"
            elif ganancia > 1.0:
                veredicto = "🟡 ganancia marginal sobre alertar a ciegas"
            else:
                veredicto = ("🔴 SIN ganancia: alertar SIEMPRE habría rendido "
                             "igual o mejor — la asertividad de arriba aún no "
                             "es habilidad")
            lineas += [
                "## 🎯 ¿Le ganamos a alertar siempre? — línea base de Molchan",
                "",
                "> La prueba de honestidad definitiva: un bot sin cerebro que "
                "alerta SIEMPRE acierta cada vez que hay un sismo cerca de la "
                "malla en la ventana de 72 h. Su tasa de acierto es la **tasa "
                "base**. Solo si el sistema supera esa tasa hay habilidad "
                "real; si no, el número bonito es geografía, no predicción.",
                "",
                "| Métrica | Valor |",
                "|---|---:|",
                f"| Ventanas evaluadas (viva) | {total_n} |",
                f"| Ventanas con evento real (tasa base) | {base:.0%} |",
                f"| Asertividad del sistema | {viva_n:.0%} |",
                f"| **Ganancia** (sistema ÷ tasa base) | "
                f"{f'{ganancia:.2f}×' if ganancia is not None else '—'} |",
                "",
                f"**Veredicto:** {veredicto}",
                "",
                "*Con 50 nodos reales y radio de 5°, casi toda ventana de 72 h "
                "tiene un M4.5+ cerca de algún nodo: para ganar de verdad, las "
                "predicciones tendrán que volverse específicas por nodo, no "
                "globales.*",
                "",
            ]
    except sqlite3.OperationalError:
        pass

    # ── Detecciones recientes ──
    dets = conn.execute(
        "SELECT tipo, display_name, confidence, station FROM TBL_DETECCIONES "
        "ORDER BY id DESC LIMIT 8"
    ).fetchall()
    if dets:
        lineas += [
            "## 🔭 Detecciones recientes — las señales individuales",
            "",
            "> Cada fila es una señal concreta que el escáner encontró en los "
            "datos: una perturbación magnética, un enjambre sísmico, un pico "
            "de gas volcánico… La **confianza** dice qué tan clara fue la "
            "señal (no la probabilidad de un evento). Una detección aislada "
            "es normal; varias juntas de tipos distintos es lo que sube el "
            "riesgo.",
            "",
            "| Precursor | Confianza | Zona |",
            "|---|---|---|",
        ]
        for d in dets:
            lineas.append(
                f"| {d[1]} | {d[2]:.0%} `{_barra(d[2], 5)}` | {d[3] or '—'} |"
            )
        lineas.append("")

    # ── Firma matches (memoria de 30 años) ──
    matches = conn.execute(
        "SELECT detalles_json, timestamp FROM TBL_JUEZ_AUDITORIA "
        "WHERE bot_name = 'padre' AND detalles_json LIKE '%firma_matches%' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if matches:
        det = json.loads(matches[0])
        fm = det.get("firma_matches", [])
        if fm:
            lineas += [
                "## 🎯 Firma Match — la memoria reconoce el momento actual",
                "",
                "> Esta es la parte más importante del reporte. Durante el "
                "entrenamiento, el sistema estudió los **14 días previos** a "
                "cada sismo fuerte de los últimos 32 años y guardó el 'rostro' "
                "de esas vísperas como una **firma**. Aquí compara el estado "
                "actual del planeta contra esa memoria. Un match del 84% "
                "significa: *lo que estamos viendo hoy se parece en un 84% a "
                "cómo se veían los días previos a ese tipo de evento*. "
                "**Veces vista** = cuántas veces esa misma firma precedió a un "
                "evento real en el histórico — a más repeticiones, más "
                "confiable el parecido.",
                "",
                "| Parecido | Precedió a | Zona (nodo de la malla) | Veces vista | Suele avisar con |",
                "|---|---|---|---|---|",
            ]
            nodos = {
                r[0]: (r[1], r[2], r[3], r[4])
                for r in conn.execute(
                    "SELECT node_id, nombre, lat, lon, region "
                    "FROM TBL_NODOS_TOPOLOGIA"
                ).fetchall()
            }
            for m in fm[:5]:
                # Lag propio de la firma si ya lo tiene medido; si no, el
                # típico de su clase de evento (ventana_tipica_dias).
                lag_dias = None
                fid = m.get("firma_id")
                if fid is not None:
                    try:
                        r = conn.execute(
                            "SELECT lag_promedio_h, lag_n FROM TBL_FIRMAS "
                            "WHERE id = ?",
                            (fid,),
                        ).fetchone()
                        if r and r[0] and (r[1] or 0) > 0:
                            lag_dias = r[0] / 24
                    except sqlite3.OperationalError:
                        pass
                if lag_dias is None:
                    lag_dias = m.get("ventana_tipica_dias")
                if lag_dias is None:
                    try:
                        r = conn.execute(
                            "SELECT lag_promedio_h FROM tbl_lag_anticipacion "
                            "WHERE event_class = ?",
                            (m.get("event_class"),),
                        ).fetchone()
                        if r and r[0]:
                            lag_dias = r[0] / 24
                    except sqlite3.OperationalError:
                        pass
                lag_txt = f"~{lag_dias:.0f} días" if lag_dias else "—"
                nodo = nodos.get(m["id_nodo"])
                if nodo:
                    lugar = (
                        f"**{nodo[0]}** ({nodo[1]:.1f}, {nodo[2]:.1f}) "
                        f"· nodo {m['id_nodo']}"
                    )
                else:
                    lugar = f"nodo {m['id_nodo']}"
                lineas.append(
                    f"| **{m['similitud']:.0%}** `{_barra(m['similitud'], 5)}` | "
                    f"{m['event_class']} | {lugar} | "
                    f"{m['recurrencia']:,} | {lag_txt} |"
                )
            lineas += [
                "",
                "*SISMO_M5 / M6 / M7 = sismo de magnitud 5+, 6+ o 7+. La zona "
                "es el punto de la malla global UVG-125 donde se aprendió la "
                "firma (nombre y coordenadas lat, lon); los nodos 'Ghost' son "
                "puntos teóricos de la malla sin estación física encima.*",
                "",
            ]

    # ── Lag de anticipación por tipo de evento ──
    try:
        lags = conn.execute(
            "SELECT event_class, lag_promedio_h, lag_max_h, lag_min_h, "
            "n_eventos FROM tbl_lag_anticipacion ORDER BY event_class"
        ).fetchall()
        if lags:
            lineas += [
                "## ⏱ Anticipación — con cuánto tiempo suele avisar",
                "",
                "> Medido sobre el histórico: ¿cuántos días **antes** del "
                "evento ya era reconocible su firma? No es un cronómetro "
                "exacto — es el promedio de lo que ha pasado. El hallazgo "
                "contraintuitivo: **los eventos más grandes avisan con más "
                "tiempo**. Un M7 se 'carga' durante más días que un M5.",
                "",
                "| Evento | Aviso promedio | Máximo | Mínimo | Casos medidos |",
                "|---|---|---|---|---|",
            ]
            for l in lags:
                lineas.append(
                    f"| {l[0]} | **{l[1]/24:.1f} días** | {l[2]/24:.1f} d | "
                    f"{l[3]/24:.1f} d | {l[4]} |"
                )
            lineas += [
                "",
                "*Medición in-sample sobre 32 años de histórico; la ventana "
                "de estudio llega a 14 días, así que los máximos pueden estar "
                "recortados.*",
                "",
            ]
    except sqlite3.OperationalError:
        pass

    # ── Factores: qué distingue firmas lentas de rápidas ──
    try:
        fact = conn.execute(
            "SELECT feature, media_rapidas, media_lentas, diferencia_norm "
            "FROM tbl_factores_lag ORDER BY ABS(diferencia_norm) DESC LIMIT 6"
        ).fetchall()
        if fact:
            lineas += [
                "## 🔍 ¿Qué acelera o retrasa un evento?",
                "",
                "> Comparamos las firmas que avisaron con **poco** tiempo "
                "(rápidas) contra las que avisaron con **mucho** (lentas). "
                "El patrón que salió: cuando hay tormenta geomagnética, el "
                "evento llega pronto — *la tormenta precipita*. Cuando el "
                "espacio está en calma, la corteza se carga despacio y avisa "
                "con más días — *la calma carga*.",
                "",
                "| Variable | En firmas rápidas | En firmas lentas | Qué indica |",
                "|---|---|---|---|",
            ]
            for f in fact:
                nombre = NOMBRES_LLANOS.get(f[0], f[0])
                sesgo = (
                    "más presente cuando el aviso es LARGO"
                    if f[3] > 0
                    else "más presente cuando el evento llega PRONTO"
                )
                lineas.append(
                    f"| {nombre} | {f[1]:.2f} | {f[2]:.2f} | {sesgo} |"
                )
            lineas += [
                "",
                "*Rápidas = tercio de firmas con menor anticipación; lentas = "
                "tercio con mayor.*",
                "",
            ]
    except sqlite3.OperationalError:
        pass

    # ── Memoria y disciplina ──
    firmas = conn.execute(
        "SELECT bot_name, COUNT(*), SUM(recurrencia) FROM TBL_FIRMAS "
        "GROUP BY bot_name ORDER BY bot_name"
    ).fetchall()
    pesos = {
        r[0]: r[1]
        for r in conn.execute("SELECT bot_name, peso FROM TBL_PESOS_BOTS").fetchall()
    }
    if firmas:
        lineas += [
            "## 🧠 Memoria entrenada — lo que el sistema ya aprendió",
            "",
            "> El sistema son **7 bots especializados**: `alfa1` vigila el "
            "clima espacial (30 años), `beta1` la resonancia Schumann — el "
            "latido electromagnético de la Tierra (30 años), `alfa2` los "
            "satélites Sentinel (aprende en vivo, sin backcast), `beta2` la "
            "desgasificación volcánica y la atmósfera (14 años), `delta` el "
            "humor de los mercados (10 años), `jupiter` la atención colectiva "
            "sobre tormentas solares (en vivo), y `padre` arbitra entre todos. "
            "Cada uno guarda sus propias **firmas** (patrones de vísperas de "
            "evento). El **peso** es su credibilidad ante el padre: 1.00 = "
            "normal; baja cuando falla y se recupera cuando acierta; puede "
            "superar 1.00 solo si detectó algo que el padre dejó pasar. "
            "`alfa2` y `jupiter` acumulan sus firmas desde los ciclos "
            "operativos, no desde el backcast histórico.",
            "",
            "| Bot | Firmas aprendidas | Veces confirmadas | Credibilidad |",
            "|---|---|---|---|",
        ]
        for f in firmas:
            p = pesos.get(f[0], 1.0)
            lineas.append(
                f"| {f[0]} | {f[1]:,} | {f[2]:,} | {p:.2f} `{_barra(p / 1.5, 6)}` |"
            )

        # alfa2 y jupiter acumulan firmas en vivo (sin backcast): si aún no tienen
        # firmas, mostrarlos igual con su estado operativo para que no "desaparezcan".
        mostrados = {f[0] for f in firmas}
        if "alfa2" not in mostrados:
            cob = conn.execute(
                "SELECT COUNT(DISTINCT timestamp_blk), COALESCE(SUM(total_passes), 0) "
                "FROM tbl_cobertura_satelital"
            ).fetchone()
            ciclos = (cob[0] if cob else 0) or 0
            pases = (cob[1] if cob else 0) or 0
            p = pesos.get("alfa2", 1.0)
            if not ciclos:
                estado = "en vivo · esperando cobertura satelital"
            elif pases == 0:
                estado = (f"en vivo · {ciclos} ciclos · sin feed satelital "
                          f"(instalar eodag + credenciales Copernicus)")
            else:
                estado = f"en vivo · {ciclos} ciclos · {pases} pases observados"
            lineas.append(f"| alfa2 | _{estado}_ | — | {p:.2f} `{_barra(p / 1.5, 6)}` |")
        if "jupiter" not in mostrados:
            p = pesos.get("jupiter", 1.0)
            lineas.append(f"| jupiter | _en vivo · atención colectiva_ | — | {p:.2f} `{_barra(p / 1.5, 6)}` |")

        lineas.append("")

    # ── Asertividad: global, histórica, individual y a 7 días ──
    try:
        # Histórica (backtest 30 años): contadores acumulados por bot
        hist = {
            r[0]: (r[1], r[2])
            for r in conn.execute(
                "SELECT bot_name, aciertos, fallos FROM TBL_PESOS_BOTS"
            ).fetchall()
        }
        # Viva (operación): SOLO filas fase='viva' — vara canónica viva_real
        viva_q = (
            "SELECT bot_name, resultado, COUNT(*) FROM viva_real "
            "WHERE resultado != 'PENDIENTE' {extra} "
            "GROUP BY bot_name, resultado"
        )

        def _tabla(rows):
            t = {}
            for bot, res, n in rows:
                d = t.setdefault(
                    bot, {"ACIERTO": 0, "FALLO": 0, "FALSO_POSITIVO": 0}
                )
                d[res] = n
            return t

        viva = _tabla(conn.execute(viva_q.format(extra="")).fetchall())
        hace7d = ahora.timestamp() - 7 * 86400
        viva7 = _tabla(
            conn.execute(
                viva_q.format(extra="AND timestamp >= ?"), (hace7d,)
            ).fetchall()
        )

        def _pct(a, f, fp=0):
            total = a + f + fp
            return f"{a/total:.1%}" if total else "—"

        def _viva_pct(t, bot=None):
            if bot is not None:
                d = t.get(bot)
                if not d:
                    return "—"
                return _pct(d["ACIERTO"], d["FALLO"], d["FALSO_POSITIVO"])
            a = sum(d["ACIERTO"] for d in t.values())
            f = sum(d["FALLO"] for d in t.values())
            fp = sum(d["FALSO_POSITIVO"] for d in t.values())
            return _pct(a, f, fp)

        ha = sum(v[0] for v in hist.values())
        hf = sum(v[1] for v in hist.values())

        lineas += [
            "## 🎯 Asertividad — ¿qué tan bien le ha ido?",
            "",
            "> Tres formas de medir lo mismo. **Histórica**: al repasar los "
            "32 años de datos como examen, ¿reconoció las vísperas de los "
            "eventos que ya sabemos que ocurrieron? **Viva**: desde que opera "
            "en tiempo real, cada aviso queda registrado y un auditor "
            "independiente (el Juez) lo califica 72 horas después contra los "
            "sismos que realmente ocurrieron — sin trampa posible. "
            "**7 días**: lo mismo, pero solo la última semana. La viva "
            "empieza en '—' hasta que las primeras ventanas de 72h se "
            "cierran.",
            "",
            "| Métrica | Valor |",
            "|---|---|",
            f"| **Histórica** (examen sobre 32 años) | {_pct(ha, hf)} |",
            f"| **Viva** (operación real, auditada) | {_viva_pct(viva)} |",
            f"| **Últimos 7 días** (viva) | {_viva_pct(viva7)} |",
            "",
            "### Por bot",
            "",
            "| Bot | Histórica | Viva | Viva 7d | Credibilidad |",
            "|---|---|---|---|---|",
        ]
        pesos_tbl = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT bot_name, peso FROM TBL_PESOS_BOTS"
            ).fetchall()
        }
        for bot in sorted(set(hist) | set(viva) | set(pesos_tbl)):
            h = hist.get(bot)
            lineas.append(
                f"| {bot} | {_pct(h[0], h[1]) if h else '—'} | "
                f"{_viva_pct(viva, bot)} | {_viva_pct(viva7, bot)} | "
                f"{pesos_tbl.get(bot, 1.0):.2f} |"
            )
        lineas += [
            "",
            "*La histórica mide reconocimiento de patrones dentro de los "
            "mismos datos con que se entrenó (por eso es tan alta). La viva "
            "es la prueba honesta: predicciones a futuro calificadas contra "
            "la realidad.*",
            "",
        ]
    except sqlite3.OperationalError:
        pass

    # ── Sesgo de aprendizaje: realidad vs fantasía ──
    try:
        sesgo = conn.execute(
            "SELECT bot, recon_insample, recon_causal, sesgo FROM "
            "tbl_sesgo_aprendizaje ORDER BY sesgo DESC"
        ).fetchall()
        if sesgo:
            lineas += [
                "## 🪞 Realidad vs fantasía — el sesgo de aprendizaje",
                "",
                "> La asertividad histórica alta es *in-sample*: el bot reconoce "
                "las firmas con las que se entrenó (comodidad). La columna "
                "**Causal (real)** mide lo honesto: ¿reconoció el evento con la "
                "memoria que ya tenía **antes** de que ocurriera? El **sesgo** "
                "es la diferencia — cuánto de esa competencia era fantasía. "
                "Aunque el número real sea más bajo, es la verdad.",
                "",
                "| Bot | In-sample | **Causal (real)** | Sesgo (fantasía) |",
                "|---|---|---|---|",
            ]
            for b in sesgo:
                flag = " ⚠️" if b[3] > 0.20 else (" ✅" if b[3] < 0.05 else "")
                lineas.append(
                    f"| {b[0]} | {b[1]:.1%} | **{b[2]:.1%}** | "
                    f"{b[3]:+.1%}{flag} |"
                )
            lineas += [
                "",
                "*Sesgo < 5% = el bot generaliza de verdad. Sesgo alto = su "
                "competencia era comodidad in-sample; su decisión real es más "
                "floja de lo que aparentaba.*",
                "",
            ]
    except sqlite3.OperationalError:
        pass

    # ── Mapa de calor de correlaciones aprendidas ──
    try:
        corr_rows = conn.execute(
            "SELECT event_class, feature, ratio, n_firmas "
            "FROM tbl_patrones_correlacion ORDER BY event_class, feature"
        ).fetchall()
        if corr_rows:
            event_classes = sorted(set(r[0] for r in corr_rows))
            # Pick top 8 most discriminating features by max deviation from 1.0
            feat_dev: dict = {}
            for _, feat, ratio, _ in corr_rows:
                d = abs(ratio - 1.0)
                if d > feat_dev.get(feat, 0.0):
                    feat_dev[feat] = d
            top_feats = [f for f, _ in
                         sorted(feat_dev.items(), key=lambda x: -x[1])[:8]]

            lookup = {(r[0], r[1]): r[2] for r in corr_rows}

            def _celda(ratio):
                if ratio is None:
                    return "  —  "
                if ratio >= 2.0:
                    return f"🔴{ratio:.1f}"
                if ratio >= 1.5:
                    return f"🟠{ratio:.1f}"
                if ratio >= 1.2:
                    return f"🟡{ratio:.1f}"
                if ratio >= 0.8:
                    return f"⬜{ratio:.1f}"
                return f"🔵{ratio:.1f}"

            lineas += [
                "## 🗺 Correlaciones aprendidas — qué precede a cada evento",
                "",
                "> Mapa de calor: qué tan elevada está cada variable en los "
                "**14 días previos** a cada tipo de evento comparado con su nivel "
                "habitual. 🔴≥2× · 🟠≥1.5× · 🟡≥1.2× · ⬜~normal · 🔵↓bajo. "
                "Un 🔴 en 'SO₂' para 'ERUPCION_VEI4' significa que justo antes "
                "de esas erupciones el SO₂ estaba el doble de lo normal. "
                "Un 🔵 en 'Kp' para 'SISMO_M7' confirma el Silent Trigger: "
                "los grandes sismos a veces ocurren en calma geomagnética.",
                "",
            ]

            # Header row
            short = {
                ec: ec.replace("SISMO_M", "M").replace("ERUPCION_", "🌋VEI")
                       .replace("TORMENTA_", "☀️Kp")
                for ec in event_classes
            }
            header = "| Variable |" + "".join(
                f" {short[ec]} |" for ec in event_classes
            )
            sep = "|---|" + "---|" * len(event_classes)
            lineas += [header, sep]

            for feat in top_feats:
                nombre = NOMBRES_LLANOS.get(feat, feat)[:38]
                row = f"| {nombre} |"
                for ec in event_classes:
                    row += f" {_celda(lookup.get((ec, feat)))} |"
                lineas.append(row)
            lineas.append("")
    except sqlite3.OperationalError:
        pass

    # ── Top 10 patrones del sistema ──
    try:
        top_firmas = conn.execute(
            "SELECT firma_id, bot_name, event_class, id_nodo, recurrencia, "
            "estado, lag_promedio_h FROM TBL_FIRMAS "
            "WHERE estado IN ('consolidada','recurrente') "
            "ORDER BY recurrencia DESC LIMIT 10"
        ).fetchall()
        if top_firmas:
            nodos_top = {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT node_id, nombre FROM TBL_NODOS_TOPOLOGIA"
                ).fetchall()
            }
            lineas += [
                "## 🏆 Top 10 patrones del sistema",
                "",
                "> Los **patrones más vistos** en 32 años de historia: firmas "
                "que el sistema reconoció más veces antes de un evento. "
                "Cuantas más repeticiones, más confiable es el patrón como señal. "
                "El **aviso** es el tiempo de anticipación típico que esa firma "
                "da antes del evento.",
                "",
                "| # | Evento | Bot | Zona / Nodo | Veces | Estado | Aviso |",
                "|---|---|---|---|---|---|---|",
            ]
            estado_icon = {"consolidada": "✅", "recurrente": "🔁"}
            event_icon = {
                "SISMO": "🌎", "ERUPCION": "🌋", "TORMENTA": "☀️",
                "HURACAN": "🌀", "TSUNAMI": "🌊",
            }
            for i, (fid, bot, ec, nodo_id, rec, estado, lag_h) in \
                    enumerate(top_firmas, 1):
                zona = (nodos_top.get(nodo_id) or f"nodo {nodo_id}") \
                    if nodo_id else "global"
                lag_txt = f"~{lag_h/24:.0f}d" if lag_h else "—"
                eicon = next(
                    (v for k, v in event_icon.items() if ec.startswith(k)), "📍"
                )
                lineas.append(
                    f"| {i} | {eicon} **{ec}** | {bot} | {zona} | "
                    f"{rec:,} | {estado_icon.get(estado, '🆕')} {estado} | "
                    f"{lag_txt} |"
                )
            lineas.append("")
    except sqlite3.OperationalError:
        pass

    # ── Patrones por tipo de evento — top 5 por clase ──
    try:
        event_classes_all = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT event_class FROM TBL_FIRMAS ORDER BY event_class"
            ).fetchall()
        ]
        if event_classes_all:
            nodos_ev = {
                r[0]: (r[1], r[2], r[3])
                for r in conn.execute(
                    "SELECT node_id, nombre, lat, lon FROM TBL_NODOS_TOPOLOGIA"
                ).fetchall()
            }
            lineas += [
                "## 📊 Patrones por tipo de evento — top 5 por clase",
                "",
                "> Para cada tipo de evento que el sistema ha aprendido, "
                "las 5 firmas más consolidadas: los patrones más reconocibles "
                "que preceden a ese tipo de evento. La **zona** es el nodo de "
                "la malla UVG-125 donde se aprendió la firma.",
                "",
            ]
            ev_icons = {
                "SISMO": "🌎", "ERUPCION": "🌋", "TORMENTA": "☀️",
                "HURACAN": "🌀", "TSUNAMI": "🌊",
            }
            estado_icon2 = {"consolidada": "✅", "recurrente": "🔁"}
            for ec in event_classes_all:
                firmas_ec = conn.execute(
                    "SELECT bot_name, id_nodo, recurrencia, estado, lag_promedio_h "
                    "FROM TBL_FIRMAS WHERE event_class = ? "
                    "ORDER BY recurrencia DESC LIMIT 5",
                    (ec,),
                ).fetchall()
                if not firmas_ec:
                    continue
                eicon = next(
                    (v for k, v in ev_icons.items() if ec.startswith(k)), "📍"
                )
                lineas += [
                    f"### {eicon} {ec}",
                    "",
                    "| Bot | Zona (nodo de la malla) | Veces vista | Estado | Aviso típico |",
                    "|---|---|---|---|---|",
                ]
                for bot, nodo_id, rec, estado, lag_h in firmas_ec:
                    if nodo_id and nodo_id in nodos_ev:
                        n = nodos_ev[nodo_id]
                        zona = f"{n[0]} ({n[1]:.1f}, {n[2]:.1f})"
                    else:
                        zona = f"nodo {nodo_id}" if nodo_id else "global"
                    lag_txt = f"~{lag_h/24:.0f} días" if lag_h else "—"
                    lineas.append(
                        f"| {bot} | {zona} | {rec:,} | "
                        f"{estado_icon2.get(estado, '🆕')} {estado} | "
                        f"{lag_txt} |"
                    )
                lineas.append("")
    except sqlite3.OperationalError:
        pass

    # ── Orden de los precursores: ¿la secuencia importa? ──
    try:
        ordenes = conn.execute(
            "SELECT conjunto, n_total, orden_dominante, frac_dominante, "
            "veredicto FROM tbl_orden_veredictos "
            "WHERE veredicto NOT LIKE 'SIN VEREDICTO%' "
            "ORDER BY n_total DESC LIMIT 6"
        ).fetchall()
        if ordenes:
            lineas += [
                "## 🔀 Orden de los precursores — ¿importa la secuencia?",
                "",
                "> El Padre también observa el **orden** en que se activaron "
                "los dominios en la víspera de cada evento (¿primero el gas y "
                "luego los sismos, o al revés?) y discierne contando: si una "
                "secuencia domina claramente, el orden IMPORTA; si las "
                "permutaciones se reparten parejo, es INDIFERENTE — lo que "
                "pesa es la convergencia, no la coreografía.",
                "",
                "| Conjunto de dominios | Casos | Secuencia dominante | % | Veredicto |",
                "|---|---:|---|---:|---|",
            ]
            for o in ordenes:
                lineas.append(
                    f"| {o[0]} | {o[1]:,} | {o[2]} | {o[3]:.0%} | "
                    f"**{o[4]}** |"
                )
            lineas.append("")
    except sqlite3.OperationalError:
        pass

    # ── Secuencia de nodos: la ruta por la que se mueve la energía ──
    try:
        rutas = conn.execute(
            "SELECT secuencia, frecuencia_total, n_clases, alcance, interpretacion "
            "FROM tbl_secuencia_veredictos ORDER BY (alcance='GLOBAL') DESC, "
            "frecuencia_total DESC LIMIT 8"
        ).fetchall()
        if rutas:
            n_global = sum(1 for r in rutas if r[3] == "GLOBAL")
            lineas += [
                "## 🌐 Cimática: cómo se mueve la energía por la malla",
                "",
                "> Más allá de *qué* nodos se activan, importa **en qué orden** "
                "espacial — la ruta por la que la energía se propaga antes de un "
                "evento. Una ruta que se repite ante **distintos tipos** de "
                "evento es **GLOBAL**: confirma una cimática organizada, un "
                "sistema liberando energía con precursores y gatillos "
                "identificables. Una ruta ligada a un solo tipo es **LOCAL** — "
                "una causa específica de ese nodo o región.",
                "",
                f"**{n_global}** de las {len(rutas)} rutas recurrentes mostradas "
                f"son globales (cimática organizada).",
                "",
                "| Ruta de propagación | Apariciones | Tipos de evento | Alcance |",
                "|---|---:|---:|---|",
            ]
            for r in rutas:
                marca = "🌐 **GLOBAL**" if r[3] == "GLOBAL" else "📍 LOCAL"
                lineas.append(
                    f"| {r[0]} | {r[1]:,} | {r[2]} | {marca} |"
                )
            lineas.append("")
    except sqlite3.OperationalError:
        pass

    # ── Auditoría del Juez — separada por fase (viva vs entrenamiento) ──
    try:
        juez_fases = conn.execute(
            "SELECT fase, resultado, COUNT(*) FROM TBL_JUEZ_AUDITORIA "
            "GROUP BY fase, resultado"
        ).fetchall()
    except sqlite3.OperationalError:
        juez_fases = [
            ("viva", r, n) for r, n in conn.execute(
                "SELECT resultado, COUNT(*) FROM TBL_JUEZ_AUDITORIA "
                "GROUP BY resultado").fetchall()
        ]
    if juez_fases:
        traduccion = {
            "ACIERTO": "ACIERTO — avisó y el evento ocurrió",
            "FALLO": "FALLO — el evento ocurrió sin aviso (lo más castigado)",
            "FALSO_POSITIVO": "FALSO POSITIVO — avisó y no pasó nada",
            "PENDIENTE": "PENDIENTE — ventana de 72h aún abierta",
        }
        vivas = {r: n for f, r, n in juez_fases if f == "viva"}
        entren = {}
        for f, r, n in juez_fases:
            if f != "viva":
                entren[r] = entren.get(r, 0) + n
        lineas += [
            "## ⚖️ El Juez — auditoría independiente",
            "",
            "> El Juez es un auditor que **nunca predice**: solo registra "
            "cada aviso de los bots y, cuando se cierra la ventana de 72 "
            "horas, lo compara contra el catálogo sísmico real (USGS) y "
            "dicta sentencia. Dejar pasar un evento castiga 10 veces más "
            "que una falsa alarma — preferimos un sistema nervioso a uno "
            "dormido. **Solo la fase viva puntúa asertividad**; el resto es "
            "bitácora de entrenamiento y no se mezcla.",
            "",
            "**Operación viva (lo que cuenta):**",
        ]
        for r in ("ACIERTO", "FALLO", "FALSO_POSITIVO", "PENDIENTE"):
            if vivas.get(r):
                lineas.append(f"- {traduccion[r]}: {vivas[r]:,}")
        if entren:
            lineas += [
                "",
                "**Bitácora de entrenamiento (reconocimiento/backtest/"
                "trasfondo — no puntúa):**",
            ]
            for r, n in sorted(entren.items()):
                lineas.append(f"- {r}: {n:,}")
        lineas.append("")

    # ── 🧾 Bitácora del sistema: versión, cambios y salud entre cortes ──
    # Cada corte guarda su instantánea en tbl_salud_sistema y se compara con
    # el corte anterior: así el reporte deja traza de la evolución del propio
    # Sentinel (¿el 43% vivo de hoy es mejor o peor que hace 10 ciclos?) y
    # permite post-mortems robustos.
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tbl_salud_sistema ("
            "ts REAL PRIMARY KEY, version TEXT, fantasma REAL, viva REAL, "
            "aciertos INTEGER, fallos INTEGER, pendientes INTEGER, "
            "pesos_json TEXT, creada_at TEXT DEFAULT (datetime('now')))"
        )
        version_modelo = "—"
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent.parent))
            from sentinel_omega.config.sentinel_config import SentinelOmegaConfig
            version_modelo = SentinelOmegaConfig().version
        except Exception:
            pass

        pesos_now = dict(conn.execute(
            "SELECT bot_name, peso FROM TBL_PESOS_BOTS").fetchall())
        juez_now = dict(conn.execute(
            "SELECT resultado, COUNT(*) FROM viva_real "
            "GROUP BY resultado").fetchall())
        aciertos_now = juez_now.get("ACIERTO", 0)
        fallos_now = juez_now.get("FALLO", 0)
        pend_now = juez_now.get("PENDIENTE", 0)
        _tot = aciertos_now + fallos_now + juez_now.get("FALSO_POSITIVO", 0)
        viva_now = (aciertos_now / _tot) if _tot else None
        fant_now = ciclo[3] if ciclo else None

        previo_salud = conn.execute(
            "SELECT ts, version, fantasma, viva, aciertos, fallos, pendientes, "
            "pesos_json FROM tbl_salud_sistema ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        historia = conn.execute(
            "SELECT viva FROM tbl_salud_sistema ORDER BY ts DESC LIMIT 5"
        ).fetchall()

        lineas += [
            "## 🧾 Bitácora del sistema — versión, cambios y salud",
            "",
            "> No solo el planeta: el propio Sentinel deja traza. Cada corte "
            "registra versión, pesos y métricas, y se compara con el corte "
            "anterior — así se ve si un cambio mejoró o empeoró el "
            "comportamiento, y los post-mortems tienen base.",
            "",
            f"| Campo | Este corte | Corte anterior | Cambio |",
            f"|---|---|---|---|",
        ]

        def _delta(a, b, fmt="{:+.1f}"):
            if a is None or b is None:
                return "—"
            return fmt.format(a - b)

        prev_ver = previo_salud[1] if previo_salud else None
        lineas.append(
            f"| Versión del modelo | {version_modelo} | {prev_ver or '—'} | "
            f"{'sin cambio' if prev_ver == version_modelo else ('**CAMBIÓ**' if prev_ver else '—')} |")
        lineas.append(
            f"| Asertividad viva | "
            f"{f'{viva_now:.1%}' if viva_now is not None else '—'} | "
            f"{f'{previo_salud[3]:.1%}' if previo_salud and previo_salud[3] is not None else '—'} | "
            f"{_delta(viva_now, previo_salud[3] if previo_salud else None, '{:+.1%}')} |")
        prev_aciertos = f"{previo_salud[4]:,} / {previo_salud[5]:,}" if (previo_salud and previo_salud[4] is not None and previo_salud[5] is not None) else "—"
        lineas.append(
            f"| Aciertos / Fallos (vivos) | {aciertos_now:,} / {fallos_now:,} | "
            f"{prev_aciertos} | "
            f"{_delta(float(aciertos_now), float(previo_salud[4]) if (previo_salud and previo_salud[4] is not None) else None, '{:+.0f}') } aciertos |")
        prev_pend = f"{previo_salud[6]:,}" if (previo_salud and previo_salud[6] is not None) else "—"
        lineas.append(
            f"| Pendientes de auditoría | {pend_now:,} | "
            f"{prev_pend} | "
            f"{_delta(float(pend_now), float(previo_salud[6]) if (previo_salud and previo_salud[6] is not None) else None, '{:+.0f}')} |")

        # Movimiento de pesos por bot (disciplina en acción)
        if previo_salud and previo_salud[7]:
            pesos_prev = json.loads(previo_salud[7])
            movidos = []
            for bot, p in sorted(pesos_now.items()):
                pp = pesos_prev.get(bot)
                if pp is not None and abs(p - pp) > 0.001:
                    movidos.append(f"{bot} {pp:.2f}→{p:.2f}")
            lineas.append(
                f"| Pesos de bots | {len(pesos_now)} bots | — | "
                f"{'; '.join(movidos) if movidos else 'sin movimiento'} |")
        else:
            lineas.append(
                f"| Pesos de bots | "
                f"{', '.join(f'{b} {p:.2f}' for b, p in sorted(pesos_now.items()))} "
                f"| — | primera bitácora |")

        if len(historia) > 1:
            trend = " → ".join(
                f"{h[0]:.0%}" if h[0] is not None else "—"
                for h in reversed(historia))
            lineas.append("")
            lineas.append(f"*Asertividad viva, últimos cortes: {trend}*")
        lineas.append("")

        # Guardar la instantánea de ESTE corte (al final, para comparar el próximo)
        conn.execute(
            "INSERT OR REPLACE INTO tbl_salud_sistema "
            "(ts, version, fantasma, viva, aciertos, fallos, pendientes, pesos_json) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ahora.timestamp(), version_modelo, fant_now, viva_now,
             aciertos_now, fallos_now, pend_now, json.dumps(pesos_now)))
        conn.commit()
    except sqlite3.OperationalError:
        pass

    total_ciclos = conn.execute("SELECT COUNT(*) FROM TBL_CICLOS").fetchone()[0]

    # ── Sección de aciertos ──
    try:
        lineas.append("")
        lineas.append(seccion_aciertos_markdown(db_path, dias=30))
    except Exception as e:
        import logging
        logging.warning(f"Error agregando sección de aciertos: {e}")

    lineas += [
        "---",
        "*Todos los datos provienen de fuentes públicas oficiales (NOAA, "
        "USGS, NASA, ESA). Nada aquí es un pronóstico oficial de protección "
        "civil: es investigación de precursores en curso.*",
        "",
        f"*Ciclos totales: {total_ciclos:,} · Sentinel Omega · Fractal Core Research*",
    ]

    conn.close()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    contenido = "\n".join(lineas) + "\n"
    out.write_text(contenido, encoding="utf-8")

    # Versionado: cada corte queda guardado en estado/historial/AAAA/MM/
    # con fecha y hora local (UTC-6) en el nombre. El operador va vaciando
    # carpetas viejas cuando quiera; REPORTE.md siempre es el último.
    from datetime import timedelta
    local = ahora - timedelta(hours=6)
    version_dir = out.parent / "historial" / local.strftime("%Y") / local.strftime("%m")
    version_dir.mkdir(parents=True, exist_ok=True)
    version_file = version_dir / f"{local.strftime('%Y-%m-%d_%H-%M')}_MX.md"
    version_file.write_text(contenido, encoding="utf-8")

    print(f"Reporte generado: {out}")
    print(f"Versión guardada: {version_file}")
    return contenido


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else DB_DEFAULT
    out = sys.argv[2] if len(sys.argv) > 2 else OUT_DEFAULT
    generar(db, out)
