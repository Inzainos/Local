"""
Beta-1 Agent — The Artist (Cymatic Figure Generator)
Role: Generate the "Cymatic Signature" of the current system state.
Method: Captures a high-fidelity snapshot of the telemetric bands (spectral, lunar, Schumann)
         and formats it as a "Figure" to be interpreted by Beta-2.

This agent does not decide if an event is likely; it only describes the current
vibrational pattern (The Figure).
"""

import numpy as np
from typing import Any, Dict, Optional
from sentinel_omega.core.shared.agent_base import BaseAgent, AgentSignal, SignalType

LOD_REF_MS: float = 3.0
MIN_CICLOS_LUNARES = 3

def kp_spectral_features(power_spectrum: np.ndarray, sample_interval_s: float) -> Dict[str, Any]:
    n_fft = len(power_spectrum)
    total_energy = float(np.sum(power_spectrum[1:]))
    if n_fft < 2 or total_energy < 1e-10:
        return {"total_energy": 0.0, "high_freq_ratio": 0.0, "dominant_period_h": 0.0}

    dominant_idx = int(np.argmax(power_spectrum[1:]) + 1)
    n_signal = 2 * (n_fft - 1)
    dominant_period_h = ((n_signal * sample_interval_s / 3600.0) / dominant_idx if dominant_idx > 0 else 0.0)
    high = float(np.sum(power_spectrum[n_fft // 2:]))
    return {"total_energy": total_energy, "high_freq_ratio": high / total_energy, "dominant_period_h": float(dominant_period_h)}

class Beta1Agent(BaseAgent):
    FFT_WINDOW_H = 48
    KP_SAMPLE_INTERVAL_H = 3

    def __init__(self):
        super().__init__(name="beta1", layer="geodynamic")
        self._kp_series: Optional[np.ndarray] = None
        self._lod_ms: Optional[np.ndarray] = None
        self._lunar_phase: Optional[np.ndarray] = None
        self._schumann_hz: float = 7.83
        self._schumann_activity: float = 0.0

    def ingest(self, data: Dict[str, Any]) -> None:
        self._kp_series = data.get("kp_series")
        self._lod_ms = data.get("lod_ms")
        self._lunar_phase = data.get("lunar_phase")
        self._schumann_hz = data.get("schumann_frequency", 7.83)
        self._schumann_activity = data.get("schumann_activity", 0.0)
        self.logger.info("Beta-1 (Artist) data ingested")

    def _generate_cymatic_figure(self) -> Dict[str, Any]:
        """
        Generates the "Figure": a compressed vector of the current system vibration.
        This is the "Drawing" that Beta-2 will interpret.
        """
        if self._kp_series is not None:
            window = self._kp_series[-self.FFT_WINDOW_H:]
            power_spectrum = np.abs(np.fft.rfft(window)) ** 2
            spec = kp_spectral_features(power_spectrum, self.KP_SAMPLE_INTERVAL_H * 3600)
        else:
            spec = {"total_energy": 0.0, "high_freq_ratio": 0.0, "dominant_period_h": 0.0}

        fase_luna = float(np.clip(self._lunar_phase[-1], 0.0, 1.0)) if self._lunar_phase is not None else 0.5
        lod_last = float(np.clip(1.0 - (self._lod_ms[-1] / LOD_REF_MS), 0.0, 1.0)) if self._lod_ms is not None else 1.0

        figure = {
            "spectral_energy": spec["total_energy"],
            "high_freq_ratio": spec["high_freq_ratio"],
            "dominant_period": spec["dominant_period_h"],
            "schumann_activity": self._schumann_activity,
            "schumann_hz": self._schumann_hz,
            "lunar_phase": fase_luna,
            "earth_rotation": lod_last,
            "composite_vibration": (spec["high_freq_ratio"] * self._schumann_activity) / 100.0
        }
        return figure

    def analyze(self) -> AgentSignal:
        if self._kp_series is None:
            return self.emit_signal(SignalType.NO_SIGNAL, 0.0)

        figure = self._generate_cymatic_figure()
        
        confidence = 0.3
        if figure["composite_vibration"] > 0.5:
            confidence = 0.6
        
        return self.emit_signal(
            SignalType.WATCH, confidence,
            data={"cymatic_figure": figure},
            reasoning="Cymatic figure generated for Beta-2 interpretation"
        )

    def health_check(self) -> bool:
        return self._kp_series is not None and len(self._kp_series) >= self.FFT_WINDOW_H
