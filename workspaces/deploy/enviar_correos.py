"""
Despacho del outbox de correo (tbl_correo_salida) — Roy Vigilante, cada corrida.

Sin credenciales SMTP los correos quedan PENDIENTES (fail-soft): nada se
pierde ni se marca enviado sin estarlo. Secrets del repo:
  SMTP_USER / SMTP_PASS (app password de Gmail) — opcionales SMTP_HOST/PORT
  CORREO_DESTINO (default elan.zainos.corona@gmail.com)
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
    from sentinel_omega.infrastructure.api.correo import enviar_pendientes
    conn = sqlite3.connect(DB)
    r = enviar_pendientes(conn)
    print(
        f"Correo: {r['enviados']} enviados, {r['pendientes']} pendientes, "
        f"{r['fallidos']} fallidos"
    )


if __name__ == "__main__":
    main()
