#!/usr/bin/env python3
"""
Tuning periódico de la base — para que no se desactualice.

  --diario   ANALYZE + PRAGMA optimize (ligero, rápido) — fin de cada día.
  --mensual  VACUUM + ANALYZE (rebuild: defragmenta y recupera disco) — fin
             de mes. Reconstruye las estadísticas del planner tras un mes de
             escrituras.

ANALYZE mantiene al planner con estadísticas frescas (clave tras los índices
nuevos); VACUUM compacta el archivo y recupera el espacio liberado por las
podas/normalización. Se agenda en roy-vigilante.yml.
"""

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DB = str(RAIZ / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("tuning")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--diario", action="store_true")
    ap.add_argument("--mensual", action="store_true")
    args = ap.parse_args()

    if not Path(DB).exists():
        logger.warning(f"Base no encontrada: {DB}")
        return

    conn = sqlite3.connect(DB, timeout=120)
    conn.execute("PRAGMA busy_timeout=120000")
    t0 = time.time()
    tam_antes = round(Path(DB).stat().st_size / 1e6, 1)

    if args.mensual:
        logger.info("Tuning MENSUAL: VACUUM + ANALYZE (rebuild)")
        try:
            conn.execute("VACUUM")
        except sqlite3.OperationalError as e:
            logger.warning(f"VACUUM omitido ({e})")
        conn.execute("ANALYZE")
    else:   # diario por defecto
        logger.info("Tuning DIARIO: ANALYZE + optimize")
        conn.execute("ANALYZE")
        conn.execute("PRAGMA optimize")

    conn.commit()
    conn.close()
    tam_desp = round(Path(DB).stat().st_size / 1e6, 1)
    logger.info(f"Tuning listo en {time.time()-t0:.0f}s "
                f"(DB {tam_antes} → {tam_desp} MB)")


if __name__ == "__main__":
    main()
