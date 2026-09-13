"""Shared ONNX load + predict helpers for geodynamic agents."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np

from sentinel_omega.core.shared.agent_base import AgentSignal, SignalType

logger = logging.getLogger(__name__)

_SIGNAL_MAP = {
    "NO_SIGNAL": SignalType.NO_SIGNAL,
    "NEUTRAL": SignalType.NEUTRAL,
    "WATCH": SignalType.WATCH,
    "ALERT": SignalType.ALERT,
    "BULLISH": SignalType.BULLISH,
    "BEARISH": SignalType.BEARISH,
}


def try_load_onnx(bot_name: str) -> Tuple[Any, Any]:
    """Load ONNX session + inference wrapper. Returns (session, inference) or (None, None)."""
    try:
        from sentinel_omega.config.onnx_config import onnx_config
        from sentinel_omega.core.onnx_engine import ONNXBotInference, ONNXModelLoader

        cfg = getattr(onnx_config, bot_name, None)
        if cfg is None or not cfg.enabled:
            logger.info(f"{bot_name}: ONNX config missing/disabled")
            return None, None
        loader = ONNXModelLoader(onnx_config.runtime, models_dir=onnx_config.models_dir)
        session = loader.load_model(cfg)
        if session is None:
            logger.info(f"{bot_name}: sin modelo ONNX — rama de reglas activa")
            return None, None
        inference = ONNXBotInference(bot_name, cfg, session)
        logger.info(f"{bot_name}: modelo ONNX cargado — rama ML activa")
        return session, inference
    except Exception as exc:
        logger.info(f"{bot_name}: ONNX no disponible ({exc}) — rama de reglas")
        return None, None


def predict_signal(
    inference: Any,
    vector: np.ndarray,
    *,
    allow_alert: bool = True,
    allow_bullish_bearish: bool = False,
) -> Optional[Tuple[SignalType, float, str]]:
    """Run ONNX predict; map to SignalType. None → caller uses rule branch."""
    if inference is None:
        return None
    try:
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        conf, name = inference.predict(vec)
        if conf <= 0.0 or name in ("NO_SIGNAL", "UNKNOWN"):
            return None
        tipo = _SIGNAL_MAP.get(name)
        if tipo is None:
            return None
        if not allow_alert and tipo == SignalType.ALERT:
            tipo = SignalType.WATCH
            name = "WATCH"
        if not allow_bullish_bearish and tipo in (SignalType.BULLISH, SignalType.BEARISH):
            tipo = SignalType.WATCH
            name = "WATCH"
        return tipo, float(min(conf, 0.95)), name
    except Exception as exc:
        logger.warning(f"ONNX predict failed: {exc}")
        return None


def pad_vector(values: list, n: int) -> np.ndarray:
    """Fixed-length float32 vector; missing dims → 0."""
    out = np.zeros(n, dtype=np.float32)
    for i, v in enumerate(values[:n]):
        if v is None:
            continue
        try:
            fv = float(v)
            if np.isfinite(fv):
                out[i] = fv
        except (TypeError, ValueError):
            pass
    return out
