"""
Correo — alertas y reportes por email (sustituto de Telegram).

Outbox pattern sobre tbl_correo_salida:
  1. encolar_correo() — cualquier parte del sistema deja el correo en la
     tabla (ALERTA o REPORTE, con adjuntos opcionales).
  2. enviar_pendientes() — el vigilante intenta el envío real por SMTP.
     Sin credenciales el correo queda PENDIENTE (fail-soft): nunca se
     pierde ni se marca enviado sin estarlo.

Credenciales SOLO por variables de entorno (regla del proyecto):
  SMTP_HOST      (default smtp.gmail.com)
  SMTP_PORT      (default 587, STARTTLS)
  SMTP_USER      cuenta emisora (p. ej. Gmail con app password)
  SMTP_PASS      contraseña de aplicación
  CORREO_DESTINO destinatario (default elan.zainos.corona@gmail.com)
"""

import json
import logging
import os
import smtplib
import sqlite3
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

DESTINO_DEFAULT = "elan.zainos.corona@gmail.com"
MAX_INTENTOS = 5


def encolar_correo(
    conn: sqlite3.Connection,
    asunto: str,
    cuerpo: str,
    tipo: str = "ALERTA",
    adjuntos: Optional[List[str]] = None,
    destinatario: Optional[str] = None,
) -> int:
    """Deja el correo en el outbox. Devuelve correo_id."""
    destino = destinatario or os.environ.get("CORREO_DESTINO", DESTINO_DEFAULT)
    cur = conn.execute(
        "INSERT INTO tbl_correo_salida "
        "(destinatario, tipo, asunto, cuerpo, adjuntos_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (destino, tipo, asunto, cuerpo, json.dumps(adjuntos or [])),
    )
    conn.commit()
    logger.info(f"CORREO encolado [{tipo}] para {destino}: {asunto}")
    return cur.lastrowid


def _construir_mensaje(destino, asunto, cuerpo, adjuntos, remitente):
    msg = EmailMessage()
    msg["From"] = remitente
    msg["To"] = destino
    msg["Subject"] = asunto
    msg.set_content(cuerpo)
    for ruta in adjuntos:
        p = Path(ruta)
        if not p.exists():
            logger.warning(f"Adjunto no encontrado (se omite): {ruta}")
            continue
        datos = p.read_bytes()
        if p.suffix.lower() == ".png":
            msg.add_attachment(datos, maintype="image", subtype="png",
                               filename=p.name)
        else:
            msg.add_attachment(datos, maintype="application",
                               subtype="octet-stream", filename=p.name)
    return msg


def enviar_pendientes(conn: sqlite3.Connection, limite: int = 20) -> dict:
    """Intenta enviar los correos PENDIENTES por SMTP.

    Sin SMTP_USER/SMTP_PASS no se intenta nada (quedan PENDIENTES y se
    informa una sola vez por corrida). Tras MAX_INTENTOS fallidos el correo
    pasa a FALLIDO para no reintentarlo eternamente.
    """
    usuario = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    puerto = int(os.environ.get("SMTP_PORT", "587"))

    pendientes = conn.execute(
        "SELECT correo_id, destinatario, asunto, cuerpo, adjuntos_json, "
        "intentos FROM tbl_correo_salida WHERE estado = 'PENDIENTE' "
        "ORDER BY correo_id LIMIT ?", (limite,),
    ).fetchall()

    if not pendientes:
        return {"enviados": 0, "pendientes": 0, "fallidos": 0}

    if not usuario or not password:
        logger.warning(
            f"CORREO: {len(pendientes)} pendientes pero sin credenciales "
            f"SMTP (SMTP_USER/SMTP_PASS) — quedan en el outbox"
        )
        return {"enviados": 0, "pendientes": len(pendientes), "fallidos": 0}

    enviados = fallidos = 0
    try:
        with smtplib.SMTP(host, puerto, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(usuario, password)
            for cid, destino, asunto, cuerpo, adj_json, intentos in pendientes:
                try:
                    adjuntos = json.loads(adj_json or "[]")
                    msg = _construir_mensaje(destino, asunto, cuerpo,
                                             adjuntos, usuario)
                    smtp.send_message(msg)
                    conn.execute(
                        "UPDATE tbl_correo_salida SET estado='ENVIADO', "
                        "enviado_at=datetime('now'), intentos=intentos+1 "
                        "WHERE correo_id=?", (cid,))
                    enviados += 1
                except Exception as e:
                    nuevo_estado = (
                        "FALLIDO" if intentos + 1 >= MAX_INTENTOS
                        else "PENDIENTE"
                    )
                    conn.execute(
                        "UPDATE tbl_correo_salida SET estado=?, "
                        "intentos=intentos+1 WHERE correo_id=?",
                        (nuevo_estado, cid))
                    fallidos += 1
                    logger.error(f"CORREO {cid} falló: {e}")
            conn.commit()
    except Exception as e:
        logger.error(f"CORREO: conexión SMTP falló ({e}) — outbox intacto")
        return {"enviados": enviados, "pendientes": len(pendientes) - enviados,
                "fallidos": fallidos}

    logger.info(f"CORREO: {enviados} enviados, {fallidos} con error")
    return {"enviados": enviados,
            "pendientes": len(pendientes) - enviados - fallidos,
            "fallidos": fallidos}
