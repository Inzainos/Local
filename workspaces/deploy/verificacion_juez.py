"""
Pasada agendada del Juez — cada 4 horas (Roy Vigilante).

Confronta las predicciones vivas expiradas contra el catálogo USGS real
(verdad por fila: ventana de 72 h + nodos de la propia predicción) e
imprime el resumen real vs predicción.
"""

import logging
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

DB = str(RAIZ / "sentinel_omega" / "data" / "SENTINEL_OMEGA_PRO.db")


def main() -> None:
    from sentinel_omega.infrastructure.pipeline.verificacion import (
        verificar_juez,
    )
    conn = sqlite3.connect(DB)
    resultado = verificar_juez(conn, forzar=True)
    if resultado.get("saltada"):
        print(f"Verificación pospuesta: {resultado.get('motivo', 'ritmo')}")
        return
    print(
        f"Juez verificó — resueltas: {resultado['resueltas']} "
        f"{resultado['conteo']} | acumulado viva: {resultado['viva']}"
    )


if __name__ == "__main__":
    main()
