"""
Omega — lectura espacial independiente (sin sesgo fijo Shadow DOM).

Vota en el ciclo; el Padre puede no contarlo en el córum hasta que su
asertividad viva supere a la del consenso. Lee telemetría espacial y
consulta el veredicto de Beta-1 (patrones / cimática Schumann).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sentinel_omega.core.shared.agent_base import BaseAgent, AgentSignal, SignalType

logger = logging.getLogger(__name__)


class OmegaAgent(BaseAgent):
    """Bot de correlación espacial independiente."""

    def __init__(self):
        super().__init__(name="omega", layer="geodynamic")
        self._data: Dict[str, Any] = {}
        self._beta_signal: Optional[AgentSignal] = None
        self._onnx = None  # ONNXBotInference
        try:
            from sentinel_omega.core.onnx_mixin import try_load_onnx
            _sess, self._onnx = try_load_onnx("omega")
        except Exception as e:
            logger.debug(f"Omega ONNX no cargado: {e}")
            self._onnx = None

    def ingest(self, data: Dict[str, Any]) -> None:
        self._data = dict(data or {})

    def set_beta_context(self, beta_signal: Optional[AgentSignal]) -> None:
        """Consulta a Beta: qué patrón / forma de energía ve."""
        self._beta_signal = beta_signal

    def health_check(self) -> bool:
        return True

    def _feature_vector(self) -> list:
        d = self._data
        fase = float(d.get("fase_lunar") or d.get("moon_phase") or 0.0)
        sicigia = 1.0 if d.get("es_sicigia") or d.get("syzygy") else 0.0
        sch_mean = float(d.get("schumann_mean") or d.get("schumann_hz") or 7.83)
        sch_std = float(d.get("schumann_std") or 0.0)
        bz = float(d.get("bz") or d.get("bz_nT") or 0.0)
        kp = float(d.get("kp") or d.get("kp_max") or 0.0)
        wind = float(d.get("viento") or d.get("wind_kms") or 0.0)
        beta_conf = float(self._beta_signal.confidence) if self._beta_signal else 0.0
        beta_alert = 0.0
        if self._beta_signal and self._beta_signal.signal_type in (
            SignalType.ALERT, SignalType.WATCH
        ):
            beta_alert = 1.0
        return [fase, sicigia, sch_mean, sch_std, bz, kp, wind, beta_conf, beta_alert]

    def analyze(self) -> AgentSignal:
        d = self._data
        bz = float(d.get("bz") or d.get("bz_nT") or 0.0)
        kp = float(d.get("kp") or d.get("kp_max") or 0.0)
        sch = float(d.get("schumann_hz") or d.get("schumann_mean") or 7.83)
        reasoning_parts = []

        signal = SignalType.NEUTRAL
        conf = 0.2

        stress = 0.0
        if bz <= -8:
            stress += 0.35
            reasoning_parts.append(f"Bz={bz:.1f} (sur fuerte)")
        elif bz <= -5:
            stress += 0.2
            reasoning_parts.append(f"Bz={bz:.1f}")
        if kp >= 6:
            stress += 0.35
            reasoning_parts.append(f"Kp={kp:.1f}")
        elif kp >= 5:
            stress += 0.2
            reasoning_parts.append(f"Kp={kp:.1f}")
        if abs(sch - 7.83) >= 0.4:
            stress += 0.15
            reasoning_parts.append(f"Schumann={sch:.2f} Hz")

        if self._beta_signal is not None:
            if self._beta_signal.signal_type == SignalType.ALERT:
                stress += 0.25 * float(self._beta_signal.confidence)
                reasoning_parts.append(
                    f"Beta ve {self._beta_signal.signal_type.value} "
                    f"({self._beta_signal.confidence:.0%})"
                )
            elif self._beta_signal.signal_type == SignalType.WATCH:
                stress += 0.12 * float(self._beta_signal.confidence)
                reasoning_parts.append("Beta en WATCH")

        try:
            if self._onnx is not None:
                from sentinel_omega.core.onnx_mixin import pad_vector, predict_signal
                n_feat = getattr(self._onnx, "n_features", None)
                if n_feat is None:
                    cfg = getattr(self._onnx, "config", None)
                    n_feat = getattr(cfg, "input_features", 12) if cfg else 12
                vec = pad_vector(self._feature_vector(), int(n_feat))
                pred = predict_signal(self._onnx, vec)
                if pred is not None:
                    onnx_sig, onnx_conf, onnx_name = pred
                    conf = max(conf, float(onnx_conf or 0))
                    if onnx_sig in (SignalType.ALERT, SignalType.WATCH):
                        signal = onnx_sig
                        stress = max(stress, conf)
                    reasoning_parts.append(
                        f"ONNX={onnx_name}@{onnx_conf:.2f}"
                    )
        except Exception as e:
            logger.debug(f"Omega ONNX infer: {e}")

        if signal == SignalType.NEUTRAL:
            if stress >= 0.55:
                signal = SignalType.ALERT
                conf = min(0.5 + stress * 0.4, 0.92)
            elif stress >= 0.30:
                signal = SignalType.WATCH
                conf = min(0.35 + stress * 0.4, 0.75)
            else:
                signal = SignalType.NEUTRAL
                conf = max(0.15, 0.4 - stress)

        reasoning = "Omega espacial: " + (
            "; ".join(reasoning_parts) if reasoning_parts else "sin anomalía"
        )
        return self.emit_signal(
            signal, conf,
            data={
                "bz": bz, "kp": kp, "schumann": sch,
                "stress": stress,
                "beta_asked": self._beta_signal is not None,
            },
            reasoning=reasoning,
        )
