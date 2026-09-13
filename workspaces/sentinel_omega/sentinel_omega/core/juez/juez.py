"""
Juez — disciplinary audit engine over TBL_JUEZ_AUDITORIA.

Cycle contract:
  1. register_prediccion() — each cycle, what each bot/Padre said (PENDIENTE).
  2. evaluar_pendientes() — once a prediction's window expires, compare
     against observed truth (USGS events) and resolve it:
        ACIERTO         — predicted event, event happened
        FALLO           — predicted calm / stayed silent, event happened
        FALSO_POSITIVO  — predicted event, nothing happened
  3. Severity is asymmetric and recidivism-scaled: missing a KNOWN
     (consolidated) signature is the gravest failure. Falsos positivos are
     recorded but cheap — the system prefers over-alerting.
  4. The Juez never adjusts predictor weights in-cycle; its record feeds
     offline recalibration only.
"""

import json
import logging
import math
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

SEVERIDAD_FALLO_BASE = 10.0
SEVERIDAD_FALSO_POSITIVO = 1.0
SEVERIDAD_FALLO_FIRMA_CONOCIDA = 20.0  # missed a consolidated signature

ALERT_SIGNALS = ("alert", "watch")


class Juez:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ── Registro ─────────────────────────────────────────────────

    def registrar_prediccion(
        self,
        bot_name: str,
        prediccion: str,
        confianza: float,
        ventana_h: int = 72,
        detalles: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
        fase: Optional[str] = None,
    ) -> int:
        """fase es ESTRICTA (columna real): 'viva' para operación, o
        'reconocimiento'/'backtest'/'observacion' para entrenamiento. Si no
        se pasa, se toma de detalles['fase'] (compat) o default 'viva'."""
        ts = timestamp or time.time()
        fase_final = fase or (detalles or {}).get("fase") or "viva"
        cur = self._conn.execute(
            "INSERT INTO TBL_JUEZ_AUDITORIA "
            "(timestamp, bot_name, prediccion, confianza, ventana_h, "
            " detalles_json, fase) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, bot_name, prediccion, confianza, ventana_h,
             json.dumps(detalles or {}), fase_final),
        )
        self._conn.commit()
        return cur.lastrowid

    def reincidencia(self, bot_name: str) -> int:
        """Historical count of FALLOs for a bot (drives severity scaling)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM TBL_JUEZ_AUDITORIA "
            "WHERE bot_name = ? AND resultado = 'FALLO'",
            (bot_name,),
        ).fetchone()
        return row[0]

    # ── Evaluación ───────────────────────────────────────────────

    def evaluar_pendientes(
        self,
        evento_ocurrido: bool,
        verdad: str = "",
        ahora: Optional[float] = None,
        firma_conocida: bool = False,
        multiplicador: float = 1.0,
        gravedad: float = 1.0,
        fase: Optional[str] = None,
        eventos: Optional[List[Dict[str, Any]]] = None,
        zonas: Optional[Sequence[Tuple[float, float]]] = None,
        radio_deg: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """Resolve every PENDIENTE prediction whose window has expired.

        evento_ocurrido: whether a qualifying real event happened within the
        prediction window (caller checks USGS/catalog truth).
        firma_conocida: True when the missed event matched a consolidated
        signature — gravest failure class.
        fase: resolve ONLY records of this fase. El entrenamiento debe pasar
        su propia fase para no resolver (contaminar) las predicciones VIVAS
        del launcher con verdades del histórico — y viceversa.

        eventos: si se pasa, la verdad se evalúa POR FILA — un evento cuenta
        solo si cayó dentro de la ventana [ts, ts+ventana_h] de ESA
        predicción (y, si hay `zonas`, a <= radio_deg de alguna zona
        monitoreada). Cada dict: {"epoch": s, "lat": .., "lon": ..,
        "magnitude": ..}. Sin esto, un solo booleano global resuelve todas
        las filas con la misma verdad — el criterio "hubo M4.5+ en la Tierra
        en 4 días" es cierto casi siempre y convierte la asertividad en el
        modelo nulo de Molchan (alertar-siempre gana). Con `eventos`, la
        vara es honesta: ventana propia + geografía monitoreada.

        Especificidad por nodo: si la fila trae `nodos` en su detalles_json
        ([{"id":.., "lat":.., "lon":..}] — los nodos de las firmas que
        motivaron la predicción), la verdad de ESA fila se evalúa SOLO
        contra esos nodos, no contra toda la malla. Un aviso solo vale si
        acierta DÓNDE avisó — así se le gana al modelo nulo.
        """
        now = ahora or time.time()
        if fase is not None:
            pendientes = self._conn.execute(
                "SELECT id, timestamp, bot_name, prediccion, confianza, "
                "ventana_h, detalles_json "
                "FROM TBL_JUEZ_AUDITORIA WHERE resultado = 'PENDIENTE' "
                "AND fase = ?", (fase,)
            ).fetchall()
        else:
            pendientes = self._conn.execute(
                "SELECT id, timestamp, bot_name, prediccion, confianza, "
                "ventana_h, detalles_json "
                "FROM TBL_JUEZ_AUDITORIA WHERE resultado = 'PENDIENTE'"
            ).fetchall()

        resueltos = []
        for pid, ts, bot, pred, conf, ventana_h, det_json in pendientes:
            if now - ts < ventana_h * 3600:
                continue  # window still open

            fk_fila = firma_conocida
            if eventos is not None:
                zonas_fila = zonas
                es_zona_propia = False
                try:
                    det = json.loads(det_json or "{}")
                    nodos_pred = det.get("nodos") or []
                    propias = [
                        (n["lat"], n["lon"]) for n in nodos_pred
                        if n.get("lat") is not None and n.get("lon") is not None
                    ]
                    if propias:
                        zonas_fila = propias
                        es_zona_propia = True
                    # firma_conocida POR FILA: si la propia predicción traía
                    # firmas matcheadas, un fallo es fallo de firma conocida.
                    fk_fila = fk_fila or bool(det.get("firma_matches"))
                except (json.JSONDecodeError, TypeError):
                    pass
                matches = self._eventos_en_ventana(
                    eventos, ts, ventana_h, zonas_fila, radio_deg
                )
                evento_ocurrido = bool(matches)
                ambito = (
                    "nodos de la predicción" if es_zona_propia
                    else ("zonas monitoreadas" if zonas_fila else "global")
                )
                if matches:
                    mag_max = max(m.get("magnitude", 0.0) or 0.0 for m in matches)
                    gravedad = 1.0 + max(0.0, mag_max - 4.5)
                    verdad = (
                        f"{len(matches)} eventos en ventana de {ventana_h}h "
                        f"(máx M{mag_max:.1f}, {ambito})"
                    )
                else:
                    gravedad = 1.0
                    verdad = f"sin eventos en ventana de {ventana_h}h ({ambito})"

            predijo_evento = pred.lower() in ALERT_SIGNALS
            if predijo_evento and evento_ocurrido:
                resultado, severidad = "ACIERTO", 0.0
            elif predijo_evento and not evento_ocurrido:
                resultado, severidad = "FALSO_POSITIVO", SEVERIDAD_FALSO_POSITIVO
            elif not predijo_evento and evento_ocurrido:
                resultado = "FALLO"
                base = (
                    SEVERIDAD_FALLO_FIRMA_CONOCIDA
                    if fk_fila
                    else SEVERIDAD_FALLO_BASE
                )
                reincid = self.reincidencia(bot)
                # base_geo: exponential punishment for falsos negativos —
                # severity grows with the SQUARE of the error gravity.
                severidad = (
                    base
                    * (max(1.0, gravedad) ** 2)
                    * (1.0 + 0.25 * reincid)
                    * multiplicador
                )
            else:
                resultado, severidad = "ACIERTO", 0.0  # calm predicted, calm held

            reincid_final = self.reincidencia(bot) + (1 if resultado == "FALLO" else 0)
            self._conn.execute(
                "UPDATE TBL_JUEZ_AUDITORIA SET resultado = ?, severidad = ?, "
                "verdad = ?, reincidencia = ?, resuelto_at = datetime('now') "
                "WHERE id = ?",
                (resultado, severidad, verdad, reincid_final, pid),
            )
            resueltos.append({
                "id": pid, "bot_name": bot, "prediccion": pred,
                "resultado": resultado, "severidad": severidad,
            })
            if resultado == "FALLO":
                logger.warning(
                    f"JUEZ: FALLO de {bot} (severidad={severidad:.1f}, "
                    f"reincidencia={reincid_final}) — predijo '{pred}', "
                    f"ocurrió: {verdad}"
                )

        if resueltos:
            self._conn.commit()
        return resueltos

    @staticmethod
    def _eventos_en_ventana(
        eventos: List[Dict[str, Any]],
        ts: float,
        ventana_h: int,
        zonas: Optional[Sequence[Tuple[float, float]]],
        radio_deg: float,
    ) -> List[Dict[str, Any]]:
        """Eventos dentro de la ventana temporal de UNA predicción y (si hay
        zonas) a <= radio_deg euclidiano en grados de alguna zona."""
        fin = ts + ventana_h * 3600
        matches = []
        for ev in eventos:
            epoch = ev.get("epoch")
            if epoch is None or not (ts <= epoch <= fin):
                continue
            if zonas:
                elat, elon = ev.get("lat"), ev.get("lon")
                if elat is None or elon is None:
                    continue
                cerca = any(
                    math.sqrt((elat - zlat) ** 2 + (elon - zlon) ** 2) <= radio_deg
                    for zlat, zlon in zonas
                )
                if not cerca:
                    continue
            matches.append(ev)
        return matches

    # ── Reportes ─────────────────────────────────────────────────

    def resumen_por_bot(self) -> Dict[str, Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT bot_name, resultado, COUNT(*), COALESCE(SUM(severidad),0) "
            "FROM TBL_JUEZ_AUDITORIA WHERE resultado != 'PENDIENTE' "
            "GROUP BY bot_name, resultado"
        ).fetchall()

        resumen: Dict[str, Dict[str, Any]] = {}
        for bot, resultado, n, sev in rows:
            entry = resumen.setdefault(bot, {
                "ACIERTO": 0, "FALLO": 0, "FALSO_POSITIVO": 0,
                "severidad_total": 0.0,
            })
            entry[resultado] = n
            entry["severidad_total"] += sev

        for bot, entry in resumen.items():
            total = entry["ACIERTO"] + entry["FALLO"] + entry["FALSO_POSITIVO"]
            entry["asertividad"] = (
                round(entry["ACIERTO"] / total, 3) if total else 0.0
            )
        return resumen
