"""
Alfa-1 Agent — Historical Space Weather Analysis
Source: OMNI NASA SPDF (30 years, 6h resolution)
Variables: Bz (IMF Z), Solar Wind velocity/density, Proton flux

Method (honesto, v2.5.1 — código y afirmación coinciden en ambas ramas):
  - CON modelo ONNX inyectado/cargado: inferencia RandomForest→ONNX sobre
    el vector de 10 features (rama ML).
  - SIN modelo (default hoy: no hay .onnx entrenado en el repo): conditioner
    por UMBRAL de Bz — reglas fijas sobre el campo magnético interplanetario.
Role: Base conditioning — long-range correlations
"""

import numpy as np
import pandas as pd
from typing import Any, Dict, Optional

from sentinel_omega.core.shared.agent_base import BaseAgent, AgentSignal, SignalType


class Alfa1Agent(BaseAgent):

    FEATURES = [
        "bz_gsm", "plasma_speed", "proton_density",
        "proton_flux_10mev", "dst_index", "ae_index",
        "kp_index", "ap_index", "field_mag_avg", "flow_pressure"
    ]
    TARGET_WINDOW_H = 72

    def __init__(self):
        super().__init__(name="alfa1", layer="geodynamic")
        self._model = None            # sesión ONNX (inyectada o cargada)
        self._inference = None        # wrapper ONNXBotInference
        self._latest_features: Optional[np.ndarray] = None
        self._available: list = []    # columnas realmente ingeridas, en orden
        self._try_load_onnx()

    def _try_load_onnx(self) -> None:
        """Carga el modelo ONNX de alfa1 si existe en models/ (fail-soft).

        Si no hay archivo .onnx, el agente opera en la rama de umbral y lo
        dice explícitamente — nunca finge que corre ML.
        """
        try:
            from sentinel_omega.config.onnx_config import onnx_config
            from sentinel_omega.core.onnx_engine import (
                ONNXBotInference, ONNXModelLoader,
            )
            cfg = onnx_config.alfa1
            loader = ONNXModelLoader(onnx_config.runtime,
                                     models_dir=onnx_config.models_dir)
            session = loader.load_model(cfg)
            if session is not None:
                self._model = session
                self._inference = ONNXBotInference("alfa1", cfg, session)
                self.logger.info("Alfa-1: modelo ONNX cargado — rama ML activa")
            else:
                self.logger.info(
                    "Alfa-1: sin modelo ONNX — rama de umbral de Bz activa"
                )
        except Exception as e:
            self.logger.info(f"Alfa-1: ONNX no disponible ({e}) — rama de umbral")

    def set_model(self, session, inference=None) -> None:
        """Inyecta una sesión ONNX ya cargada (p. ej. desde el notebook)."""
        self._model = session
        if inference is not None:
            self._inference = inference
        else:
            try:
                from sentinel_omega.config.onnx_config import onnx_config
                from sentinel_omega.core.onnx_engine import ONNXBotInference
                self._inference = ONNXBotInference("alfa1", onnx_config.alfa1,
                                                   session)
            except Exception:
                self._inference = None

    def ingest(self, data: Dict[str, Any]) -> None:
        df = data.get("omni_dataframe")
        if df is None:
            self.logger.warning("No OMNI data provided")
            return

        available = [f for f in self.FEATURES if f in df.columns]
        self._available = available
        self._latest_features = df[available].values
        self.logger.info(f"Ingested {len(df)} OMNI records, {len(available)} features")

    def _bz_mean(self) -> Optional[float]:
        """Media de Bz por NOMBRE de columna — la posición 0 solo es Bz si
        bz_gsm venía en el dataframe; asumirlo silenciosamente corrompe la
        regla de umbral."""
        if self._latest_features is None or "bz_gsm" not in self._available:
            return None
        idx = self._available.index("bz_gsm")
        return float(np.nanmean(self._latest_features[:, idx]))

    def _analyze_onnx(self) -> Optional[AgentSignal]:
        """Rama ML: inferencia ONNX sobre el vector de features más reciente.

        Devuelve None si la inferencia no es utilizable (sin wrapper, vector
        incompleto o salida degenerada) — el caller cae a la rama de umbral.
        """
        if self._inference is None or self._latest_features is None:
            return None
        try:
            # Vector alineado por NOMBRE al orden canónico de FEATURES:
            # un pad ciego desalinearía las columnas si falta alguna.
            ultima = self._latest_features[-1]
            fila = np.zeros(len(self.FEATURES), dtype=np.float32)
            for i, feat in enumerate(self.FEATURES):
                if feat in self._available:
                    fila[i] = ultima[self._available.index(feat)]
            fila = np.nan_to_num(fila, nan=0.0)
            conf, signal_name = self._inference.predict(fila)
            tipo = {
                "ALERT": SignalType.ALERT,
                "WATCH": SignalType.WATCH,
                "NEUTRAL": SignalType.NEUTRAL,
            }.get(signal_name)
            if tipo is None or conf <= 0.0:
                return None   # salida degenerada → fallback honesto
            bz = self._bz_mean()
            return self.emit_signal(
                tipo, float(min(conf, 0.95)),
                data={"onnx": True,
                      "bz_mean": bz if bz is not None else 0.0},
                reasoning=f"ONNX inference: {signal_name} ({conf:.0%})",
            )
        except Exception as e:
            self.logger.warning(f"Alfa-1 ONNX inference failed: {e} — fallback")
            return None

    def analyze(self) -> AgentSignal:
        if self._latest_features is None:
            return self.emit_signal(SignalType.NO_SIGNAL, 0.0,
                                   reasoning="No data ingested")

        # Rama ML si hay modelo; si no, umbral de Bz (y se dice cuál corre)
        if self._model is not None:
            resultado = self._analyze_onnx()
            if resultado is not None:
                return resultado

        bz_mean = self._bz_mean()
        if bz_mean is None:
            # Sin columna bz_gsm no hay regla de Bz que aplicar — se dice.
            return self.emit_signal(
                SignalType.NEUTRAL, 0.2,
                data={"onnx": False, "bz_mean": None},
                reasoning="No bz_gsm column ingested — Bz threshold rule not applicable",
            )

        if bz_mean < -10:
            return self.emit_signal(
                SignalType.ALERT, 0.85,
                data={"onnx": False, "bz_mean": float(bz_mean)},
                reasoning=f"Bz threshold rule: severely negative ({bz_mean:.1f} nT) — geomagnetic storm conditions"
            )
        elif bz_mean < -5:
            return self.emit_signal(
                SignalType.ALERT, 0.5,
                data={"onnx": False, "bz_mean": float(bz_mean)},
                reasoning=f"Bz threshold rule: moderately negative ({bz_mean:.1f} nT) — elevated activity"
            )
        else:
            return self.emit_signal(
                SignalType.NEUTRAL, 0.3,
                data={"onnx": False, "bz_mean": float(bz_mean)},
                reasoning=f"Bz threshold rule: normal range ({bz_mean:.1f} nT)"
            )

    def health_check(self) -> bool:
        return self._latest_features is not None
