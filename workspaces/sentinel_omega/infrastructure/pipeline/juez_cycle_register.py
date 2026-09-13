"""
Register Juez predictions for Padre + every agent in agent_signals.

Called from launcher after consensus. Ventana adaptativa (2h floor, lag empírica, tope 90d).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def register_cycle_predictions(
    juez: Any,
    geo: Any,
    matches: Optional[List[Dict]] = None,
    conn: Any = None,
    muro_lags: Optional[Dict] = None,
    nodos_pred: Optional[List[Dict]] = None,
    features: Optional[Dict] = None,
) -> int:
    """
    Registers padre + per-bot predictions. Returns number of bot rows registered.

    `features` (fix 2026-08-20): snapshot de telemetría general del ciclo
    (mismo dict que produce _build_live_features() — bz_mean, kp_mean,
    fase_lunar, schumann_mean, so2_kt_win, btc_volatilidad, etc.). Se
    guarda bajo la clave "features_generales" en detalles_json de CADA
    predicción registrada (padre + cada bot). Sin esto, el reentrenamiento
    ONNX (train_onnx_from_db.py::load_juez_feedback) no tenía forma de
    reconstruir vectores de features reales desde el feedback historico
    del Juez — en particular, el feedback de "padre" (remapeado a "omega"
    para entrenamiento, porque Omega aprende de telemetría general/
    consenso, no de un dominio especifico) caía casi siempre en un vector
    vacío. Retrocompatible: filas registradas ANTES de este fix
    simplemente no tendran "features_generales" en su detalles_json.
    """
    matches = matches or []
    muro_lags = muro_lags or {}
    nodos_pred = nodos_pred or []
    features = features or {}

    ventana_h = 2

    juez.registrar_prediccion(
        bot_name="padre",
        prediccion=geo.final_signal.value,
        confianza=geo.confidence,
        ventana_h=ventana_h,
        detalles={
            "firma_matches": matches[:5],
            "muro_lags": muro_lags,
            "nodos": nodos_pred,
            "ventana_h": ventana_h,
            "features_generales": features,
        },
        fase="viva",
    )

    n_bots = 0
    for sig in (getattr(geo, "agent_signals", None) or []):
        try:
            name = getattr(sig, "agent_name", None)
            st = getattr(sig, "signal_type", None)
            conf = float(getattr(sig, "confidence", 0) or 0)
            if not name or st is None:
                continue
            pred = st.value if hasattr(st, "value") else str(st)
            juez.registrar_prediccion(
                bot_name=str(name).lower(),
                prediccion=pred,
                confianza=conf,
                ventana_h=ventana_h,
                detalles={
                    "nodos": nodos_pred,
                    "padre_signal": geo.final_signal.value,
                    "reasoning": (getattr(sig, "reasoning", "") or "")[:500],
                    "features_generales": features,
                },
                fase="viva",
            )
            n_bots += 1
        except Exception as e:
            logger.warning("No se registró predicción de bot: %s", e)
    return n_bots
