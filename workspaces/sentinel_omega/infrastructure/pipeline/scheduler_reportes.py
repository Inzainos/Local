"""
Sentinel Omega — Scheduler de Reportes
=======================================
Corre en background junto al launcher principal.
Frecuencias según los docstrings de reporte_sentinel.py:

  reporte_general()  → cada 2 horas
  reporte_padre()    → cada 6 horas
  reporte_omega()    → cada 6 horas

Uso (lanzar en background):
    python -m sentinel_omega.infrastructure.pipeline.scheduler_reportes
    python sentinel_omega/infrastructure/pipeline/scheduler_reportes.py

El postStart.sh lo arranca automáticamente en el Codespace.
"""

import io
import contextlib
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# La DB real del sistema (misma que config.databases.geodynamic_db)
DB_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data" / "SENTINEL_OMEGA_PRO.db"
)
LOG_DIR = DB_PATH.parent
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "scheduler_reportes.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)

_INTERVAL_GENERAL  = 2 * 3600   # 2 horas
_INTERVAL_PROFUNDO = 6 * 3600   # 6 horas

_shutdown = False


def _signal_handler(signum, frame):
    global _shutdown
    logger.info(f"Signal {signal.Signals(signum).name} — cerrando scheduler.")
    _shutdown = True


def _guardar(texto: str, nombre: str) -> Path:
    """Guarda el texto en data/ con timestamp y devuelve la ruta."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"{nombre}_{ts}.txt"
    path.write_text(texto, encoding="utf-8")
    return path


def _correr_reporte(fn, nombre: str) -> None:
    """Ejecuta fn(db_path), captura stdout, guarda archivo y loguea."""
    db = str(DB_PATH)
    if not DB_PATH.exists():
        logger.warning(f"{nombre}: DB no encontrada en {db} — saltando.")
        return
    logger.info(f"Generando {nombre}...")
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fn(db)
        texto = buf.getvalue()
        path = _guardar(texto, nombre)
        logger.info(f"{nombre} guardado → {path}")
    except Exception as e:
        logger.error(f"{nombre} falló: {e}", exc_info=True)


def _interruptible_sleep(seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end and not _shutdown:
        time.sleep(min(30.0, end - time.time()))


def run() -> None:
    global _shutdown

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    from sentinel_omega.infrastructure.pipeline.reporte_sentinel import (
        reporte_general,
        reporte_padre,
        reporte_omega,
    )

    logger.info("Scheduler de reportes ONLINE.")
    logger.info(f"  reporte_general  → cada {_INTERVAL_GENERAL  // 3600}h")
    logger.info(f"  reporte_padre    → cada {_INTERVAL_PROFUNDO // 3600}h")
    logger.info(f"  reporte_omega    → cada {_INTERVAL_PROFUNDO // 3600}h")
    logger.info(f"  DB: {DB_PATH}")

    # Timestamps de última ejecución (0 = nunca → corre inmediatamente la primera vez)
    last_general  = 0.0
    last_profundo = 0.0

    while not _shutdown:
        now = time.time()

        if now - last_general >= _INTERVAL_GENERAL:
            _correr_reporte(reporte_general, "reporte_general")
            last_general = time.time()

        if now - last_profundo >= _INTERVAL_PROFUNDO:
            _correr_reporte(reporte_padre, "reporte_padre")
            _correr_reporte(reporte_omega, "reporte_omega")
            last_profundo = time.time()

        _interruptible_sleep(60)  # revisa cada minuto

    logger.info("Scheduler de reportes OFFLINE.")


if __name__ == "__main__":
    run()
