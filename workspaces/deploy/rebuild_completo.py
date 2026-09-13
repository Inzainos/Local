#!/usr/bin/env python3
"""
Rebuild completo y autónomo de Sentinel Omega — corre solo, deja el reporte.

Hace TODA la chamba de una corrida en orden, sin intervención:
  1. Para cualquier launcher activo (PID).
  2. VACÍA la memoria aprendida (firmas, pesos, correlaciones, orden, sesgo,
     lags, secuencias, cimática) — se conserva la fase 'viva' del Juez
     (append-only) y TODO el backcast crudo.
  3. init_database → aplica migración 1NF (eventos_json→hija, muestreo),
     índices (incl. el compuesto), tablas nuevas y vistas.
  4. TUNING previo: ANALYZE + PRAGMA optimize (planner al día tras los
     cambios de índice).
  5. Entrenamiento completo (sesgo PRE → Fase 1 + 1b → Fase 2 → lags →
     correlaciones → cimática histórica → sesgo POST) con el código NUEVO
     (registrar normalizado, sin el O(n²) — mucho más rápido que la corrida
     vieja).
  6. Disciplina de trasfondo + barrido diario (que ahora corre TODOS los
     cruces: orden de precursores multi-bot, secuencia de nodos global/local,
     poda cimática).
  7. TUNING final: VACUUM (recupera disco de los arrays viejos) + ANALYZE.
  8. Genera el reporte y escribe un REPORTE_REBUILD.md con el resumen.

Uso:
    python deploy/rebuild_completo.py            # todo
    python deploy/rebuild_completo.py --no-wipe  # sin vaciar (continuar)

Diseñado para correr en background y sobrevivir solo:
    nohup python deploy/rebuild_completo.py > estado/rebuild.log 2>&1 &
"""

import argparse
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REBUILD] %(levelname)s %(message)s",
)
logger = logging.getLogger("rebuild")

DB = str(RAIZ / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db")
PID = RAIZ / "sentinel_omega" / "data" / "sentinel_omega.pid"
REPORTE_OUT = RAIZ / "estado" / "REPORTE_REBUILD.md"

# Memoria aprendida a vaciar (se reconstruye desde cero). NUNCA se toca la
# fase 'viva' del Juez ni el backcast crudo.
WIPE = [
    ("TBL_FIRMAS", "DELETE FROM TBL_FIRMAS"),
    ("tbl_firma_eventos", "DELETE FROM tbl_firma_eventos"),
    ("tbl_firmas_menores", "DELETE FROM tbl_firmas_menores"),
    ("TBL_PESOS_BOTS", "DELETE FROM TBL_PESOS_BOTS"),
    ("TBL_JUEZ_AUDITORIA(entren)",
     "DELETE FROM TBL_JUEZ_AUDITORIA WHERE fase != 'viva'"),
    ("tbl_correlaciones_padre", "DELETE FROM tbl_correlaciones_padre"),
    ("tbl_correlaciones_omega", "DELETE FROM tbl_correlaciones_omega"),
    ("tbl_orden_precursores", "DELETE FROM tbl_orden_precursores"),
    ("tbl_orden_veredictos", "DELETE FROM tbl_orden_veredictos"),
    ("tbl_secuencia_nodos", "DELETE FROM tbl_secuencia_nodos"),
    ("tbl_secuencia_veredictos", "DELETE FROM tbl_secuencia_veredictos"),
    ("tbl_cimatica_patrones", "DELETE FROM tbl_cimatica_patrones"),
    ("tbl_sesgo_aprendizaje", "DELETE FROM tbl_sesgo_aprendizaje"),
    ("tbl_factores_lag", "DELETE FROM tbl_factores_lag"),
    ("tbl_lag_anticipacion", "DELETE FROM tbl_lag_anticipacion"),
]

resumen: dict = {"pasos": [], "inicio": None, "fin": None}


def _paso(nombre, fn):
    t0 = time.time()
    logger.info(f"▶ {nombre}")
    try:
        detalle = fn()
        dt = time.time() - t0
        logger.info(f"✔ {nombre} ({dt:.0f}s)")
        resumen["pasos"].append({"paso": nombre, "ok": True,
                                 "seg": round(dt), "detalle": detalle})
    except Exception as e:
        dt = time.time() - t0
        logger.error(f"[X] {nombre} FALLO: {e}")
        resumen["pasos"].append({"paso": nombre, "ok": False,
                                 "seg": round(dt), "error": str(e)})


def parar_launcher():
    if PID.exists():
        try:
            import os
            import signal
            pid = int(PID.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            time.sleep(3)
        except (ProcessLookupError, ValueError, OSError):
            pass
        PID.unlink(missing_ok=True)
    return "PID limpio"


def vaciar_memoria():
    conn = sqlite3.connect(DB)
    borradas = {}
    for nombre, sql in WIPE:
        try:
            borradas[nombre] = conn.execute(sql).rowcount
        except sqlite3.OperationalError:
            borradas[nombre] = "n/a"
    conn.commit()
    conn.close()
    return borradas


def inicializar():
    from sentinel_omega.infrastructure.database.schema import init_database
    conn = init_database(DB)   # migración + índices + tablas + vistas
    conn.close()
    return "esquema, migración, índices y vistas aplicados"


def tuning(vacuum: bool):
    conn = sqlite3.connect(DB)
    if vacuum:
        conn.execute("VACUUM")
    conn.execute("ANALYZE")
    conn.execute("PRAGMA optimize")
    conn.commit()
    conn.close()
    return f"ANALYZE + optimize{' + VACUUM' if vacuum else ''}"


def entrenar():
    from sentinel_omega.infrastructure.pipeline.entrenamiento import entrenar
    return entrenar(DB)


def disciplina_y_barrido():
    from sentinel_omega.infrastructure.pipeline.entrenamiento import (
        disciplina_trasfondo,
    )
    from sentinel_omega.infrastructure.pipeline.mantenimiento import (
        barrido_diario,
    )
    out = {}
    try:
        out["disciplina"] = disciplina_trasfondo(DB)
    except Exception as e:
        out["disciplina"] = f"error: {e}"
    out["barrido"] = barrido_diario(DB)
    return out


def generar_reportes():
    import subprocess
    for script in ("generar_reporte.py", "reporte_ejecutivo.py"):
        subprocess.run([sys.executable, str(RAIZ / "deploy" / script)],
                       check=False)
    return "REPORTE.md + REPORTE_EJECUTIVO.md"


def escribir_reporte_rebuild():
    conn = sqlite3.connect(DB)

    def q1(sql, d=0):
        try:
            r = conn.execute(sql).fetchone()
            return r[0] if r and r[0] is not None else d
        except sqlite3.OperationalError:
            return d

    firmas = q1("SELECT COUNT(*) FROM TBL_FIRMAS")
    consol = q1("SELECT COUNT(*) FROM TBL_FIRMAS WHERE estado='consolidada'")
    pesos = conn.execute(
        "SELECT bot_name, ROUND(peso,3) FROM TBL_PESOS_BOTS "
        "ORDER BY bot_name").fetchall() if q1(
        "SELECT COUNT(*) FROM TBL_PESOS_BOTS") else []
    sesgo = conn.execute(
        "SELECT bot, ROUND(recon_insample,3), ROUND(recon_causal,3), "
        "ROUND(sesgo,3) FROM tbl_sesgo_aprendizaje ORDER BY bot").fetchall() \
        if q1("SELECT COUNT(*) FROM tbl_sesgo_aprendizaje") else []
    cim = q1("SELECT COUNT(*) FROM tbl_cimatica_patrones")
    glob = q1("SELECT COUNT(*) FROM tbl_secuencia_veredictos WHERE alcance='GLOBAL'")
    loc = q1("SELECT COUNT(*) FROM tbl_secuencia_veredictos WHERE alcance='LOCAL'")
    viva = dict(conn.execute(
        "SELECT resultado, COUNT(*) FROM viva_real GROUP BY resultado"
    ).fetchall()) if True else {}
    tam_mb = round(Path(DB).stat().st_size / 1e6, 1)
    conn.close()

    L = [
        "# 🔧 Rebuild completo — reporte final",
        f"*Generado {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC*",
        "",
        "## Pasos ejecutados",
        "",
        "| Paso | Estado | Tiempo |",
        "|---|---|---:|",
    ]
    for p in resumen["pasos"]:
        estado = "✅" if p["ok"] else f"❌ {p.get('error','')[:60]}"
        L.append(f"| {p['paso']} | {estado} | {p['seg']}s |")
    dur = ((resumen["fin"] or 0) - (resumen["inicio"] or 0)) / 60
    L += [
        "",
        f"**Duración total:** {dur:.0f} min · **Tamaño DB:** {tam_mb} MB",
        "",
        "## Memoria reconstruida",
        f"- Firmas: **{firmas:,}** ({consol:,} consolidadas)",
        f"- Patrones cimáticos: **{cim:,}**",
        f"- Rutas de propagación: **{glob}** globales · **{loc}** locales",
        "",
        "## Pesos por bot",
        "",
    ]
    if pesos:
        L += ["| Bot | Peso |", "|---|---:|"]
        L += [f"| {b} | {p} |" for b, p in pesos]
    else:
        L.append("*(pesos aún no calculados)*")
    L += ["", "## Sesgo de aprendizaje (realidad vs fantasía)", ""]
    if sesgo:
        L += ["| Bot | In-sample | Causal | Sesgo |", "|---|---:|---:|---:|"]
        L += [f"| {b} | {i} | {c} | {s} |" for b, i, c, s in sesgo]
    else:
        L.append("*(sesgo aún no calculado)*")
    L += [
        "", "## Asertividad viva (append-only, no se tocó)",
        f"- {viva}", "",
        "*Reporte autogenerado por deploy/rebuild_completo.py*",
    ]
    REPORTE_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORTE_OUT.write_text("\n".join(L), encoding="utf-8")
    return str(REPORTE_OUT)


def empujar_reporte(rama: str):
    """Best-effort: commitea y empuja los reportes para que la corrida
    autónoma deje el resultado en el repo aunque nadie esté mirando."""
    import subprocess

    def _run(*a):
        return subprocess.run(a, cwd=str(RAIZ), check=False,
                              capture_output=True, text=True)
    _run("git", "add", "estado/")
    r = _run("git", "diff", "--cached", "--quiet")
    if r.returncode == 0:
        return "sin cambios que empujar"
    _run("git", "-c", "user.name=roy-rebuild",
         "-c", "user.email=actions@users.noreply.github.com",
         "commit", "-m",
         f"Reporte de rebuild {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC")
    _run("git", "pull", "--rebase", "origin", rama)
    push = _run("git", "push", "origin", rama)
    return "empujado" if push.returncode == 0 else f"push falló: {push.stderr[:80]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-wipe", action="store_true",
                    help="no vaciar la memoria aprendida")
    ap.add_argument("--no-vacuum", action="store_true",
                    help="saltar VACUUM final (si el disco está justo)")
    ap.add_argument("--push", metavar="RAMA",
                    help="commitear+empujar el reporte al terminar")
    args = ap.parse_args()

    resumen["inicio"] = time.time()
    logger.info("=== REBUILD COMPLETO — inicio ===")

    _paso("Parar launcher", parar_launcher)
    if not args.no_wipe:
        _paso("Vaciar memoria aprendida", vaciar_memoria)
    _paso("init_database (migración + índices + vistas)", inicializar)
    _paso("Tuning previo (ANALYZE + optimize)", lambda: tuning(vacuum=False))
    _paso("Entrenamiento completo", entrenar)
    _paso("Disciplina + barrido (cruces)", disciplina_y_barrido)
    _paso("Tuning final (VACUUM + ANALYZE)",
          lambda: tuning(vacuum=not args.no_vacuum))
    _paso("Generar reportes", generar_reportes)

    resumen["fin"] = time.time()
    _paso("Escribir reporte del rebuild", escribir_reporte_rebuild)
    if args.push:
        _paso("Empujar reporte al repo", lambda: empujar_reporte(args.push))
    logger.info(f"=== REBUILD COMPLETO — fin ({REPORTE_OUT}) ===")


if __name__ == "__main__":
    main()
