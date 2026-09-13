#!/usr/bin/env python3
"""
Bootstrap incremental del bot Omega (una vez).

Si la DB fue entrenada antes de que Omega tuviera su mapeo de campos en
BOT_FEATURES, sus firmas están en 0. Este script lo detecta y corre el
entrenamiento incremental SOLO de omega (sin inflar la recurrencia de los
demás bots), y construye su tabla de correlaciones. Idempotente: si Omega
ya tiene firmas, no hace nada.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DB = str(
    Path(__file__).parent.parent / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db"
)


def main() -> None:
    db = sys.argv[1] if len(sys.argv) > 1 else DB
    try:
        n = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM TBL_FIRMAS WHERE bot_name='omega'"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        print("DB sin TBL_FIRMAS — nada que hacer (el bootstrap general va primero)")
        return
    if n > 0:
        print(f"Omega ya tiene {n:,} firmas — skip")
        return

    print("Omega sin firmas — entrenamiento incremental (solo omega)...")
    from sentinel_omega.infrastructure.pipeline.entrenamiento import (
        backtest_disciplinario,
        entrenar_reconocimiento,
        entrenar_reconocimiento_no_sismico,
    )
    from sentinel_omega.infrastructure.pipeline.mantenimiento import (
        construir_correlaciones_omega,
    )

    f1 = entrenar_reconocimiento(db, bots=["omega"])
    print(f"Fase 1 (omega): {f1.get('firmas_nuevas')} firmas, "
          f"{f1.get('recurrencias')} recurrencias")
    f1b = entrenar_reconocimiento_no_sismico(db, bots=["omega"])
    print(f"Fase 1b (omega): {f1b}")
    f2 = backtest_disciplinario(db, bots=["omega"])
    print(f"Fase 2 (omega): {f2.get('reconocidas')}/{f2.get('firmas_evaluadas')} "
          "reconocidas")
    print(f"Correlaciones: {construir_correlaciones_omega(db)}")


if __name__ == "__main__":
    main()
