"""
Loki Agent — Fractal-Bayesian Unified Field (Act 3)
====================================================
The third and final act of the consensus hierarchy.
Architecture: SVD (Gauss-Jordan proxy) -> FFT -> Bayesian Update with φ (Golden Ratio)
Base Node: Tlaxcala, Mexico (19.318°N, -98.237°W)
"""

import numpy as np
from typing import Any, Dict, Optional, List
from sentinel_omega.core.shared.agent_base import BaseAgent, AgentSignal, SignalType

class LokiAgent(BaseAgent):
    PHI = (1 + 5**0.5) / 2  # Golden Ratio φ = 1.618...
    TLAXCALA_LAT = 19.318
    TLAXCALA_LON = -98.237
    COLLAPSE_THRESHOLD = 0.8
    FRACTAL_DIMENSION_THRESHOLD = 1.5

    def __init__(self):
        super().__init__(name="loki", layer="geodynamic")
        self._data_vector: Optional[List[float]] = None
        self._svd_singular_values: Optional[np.ndarray] = None
        self._fft_spectrum: Optional[np.ndarray] = None
        self._fractal_dimension: float = 0.0
        self._bayesian_prior: float = 0.5
        self._bayesian_posterior: float = 0.5
        self.logger.info("Loki Agent (Fractal-Bayesian) initialized at Tlaxcala Node")

    def ingest(self, data: Dict[str, Any]) -> None:
        """Ingest multi-domain data: Bz, Solar Wind, Schumann, VIX, LOD"""
        self._data_vector = [
            float(data.get("bz", 0.0)),              # IMF Bz GSM (nT)
            float(data.get("solar_wind", 0.0)),      # Solar wind speed (km/s)
            float(data.get("schumann_activity", 0.0)), # Schumann resonance power
            float(data.get("vix", 20.0)),            # VIX fear index
            float(data.get("lod", 0.0))              # Length of Day (ms)
        ]
        self.logger.info(f"Loki: Data vector ingested: {self._data_vector}")

    def _svd_cleaning(self) -> np.ndarray:
        """Step 1: Linear Cleaning via SVD (Gauss-Jordan proxy)"""
        if self._data_vector is None:
            return np.array([])
        matrix = np.array(self._data_vector).reshape(1, -1)
        try:
            u, s, vh = np.linalg.svd(matrix, full_matrices=False)
            self._svd_singular_values = s
            return s
        except Exception as e:
            self.logger.warning(f"Loki SVD failed: {e}")
            return np.array([])

    def _fft_scan(self, singular_values: np.ndarray) -> np.ndarray:
        """Step 2: Frequency Scanning via FFT"""
        if len(singular_values) == 0:
            return np.array([])
        try:
            # Pad for better frequency resolution
            padded = np.pad(singular_values, (0, 32 - len(singular_values)), mode='constant')
            spectrum = np.abs(np.fft.fft(padded))
            self._fft_spectrum = spectrum
            return spectrum
        except Exception as e:
            self.logger.warning(f"Loki FFT failed: {e}")
            return np.array([])

    def _compute_fractal_dimension(self, spectrum: np.ndarray) -> float:
        """Estimate fractal dimension from power spectrum slope (log-log)"""
        if len(spectrum) < 4:
            return 1.0
        try:
            # Use positive frequencies only, exclude DC
            freqs = np.fft.fftfreq(len(spectrum))[1:len(spectrum)//2]
            psd = spectrum[1:len(spectrum)//2]
            # Filter out zeros
            mask = (freqs > 0) & (psd > 0)
            if np.sum(mask) < 3:
                return 1.0
            log_f = np.log(freqs[mask])
            log_p = np.log(psd[mask])
            # Linear fit: log(P) = -β log(f) + C, fractal_dim = (5-β)/2 for 1D
            coeffs = np.polyfit(log_f, log_p, 1)
            beta = -coeffs[0]
            fractal_dim = (5 - beta) / 2
            return max(1.0, min(2.0, fractal_dim))
        except Exception:
            return 1.0

    def _bayesian_update(self, prior: float, likelihood: float) -> float:
        """Step 3: Bayesian Inference with φ-weighted likelihood"""
        # P(E) global evidence baseline
        p_e = 0.1
        posterior = (likelihood * prior) / (p_e + 1e-9)
        return float(np.clip(posterior, 0.0, 1.0))

    def analyze(self) -> AgentSignal:
        if self._data_vector is None:
            return self.emit_signal(SignalType.NO_SIGNAL, 0.0, reasoning="No data vector ingested")

        # --- THE FRACTAL-BAYESIAN MASSAGE ---
        
        # 1. SVD Cleaning
        singular_values = self._svd_cleaning()
        
        # 2. FFT Resonance Scan
        spectrum = self._fft_scan(singular_values)
        
        # 3. Fractal Dimension
        self._fractal_dimension = self._compute_fractal_dimension(spectrum)
        
        # 4. Bayesian Update with φ (Golden Ratio)
        # Likelihood based on φ-alignment of resonance peak + fractal dimension
        if len(spectrum) > 0:
            peak_freq_idx = np.argmax(spectrum[1:]) + 1
            peak_magnitude = spectrum[peak_freq_idx]
            # φ-alignment: how close is peak to φ-scaled frequency?
            phi_alignment = np.exp(-abs(peak_magnitude - self.PHI) / self.PHI)
            # Combine with fractal dimension (higher dim = more complex = more significant)
            likelihood = phi_alignment * (self._fractal_dimension / 2.0)
        else:
            likelihood = 0.1
            
        self._bayesian_posterior = self._bayesian_update(self._bayesian_prior, likelihood)
        self._bayesian_prior = self._bayesian_posterior  # Update prior for next cycle

        signal_data = {
            "svd_singular_values": singular_values.tolist() if len(singular_values) > 0 else [],
            "fft_peak_magnitude": float(np.max(spectrum)) if len(spectrum) > 0 else 0.0,
            "fractal_dimension": round(self._fractal_dimension, 3),
            "bayesian_posterior": round(self._bayesian_posterior, 4),
            "bayesian_prior": round(self._bayesian_prior, 4),
            "phi_alignment": round(likelihood, 4),
            "tlaxcala_node": [self.TLAXCALA_LAT, self.TLAXCALA_LON],
            "phi": self.PHI,
        }

        # Decision logic
        if self._bayesian_posterior >= self.COLLAPSE_THRESHOLD and self._fractal_dimension >= self.FRACTAL_DIMENSION_THRESHOLD:
            reasoning = f"FRACTAL-BAYESIAN COLLAPSE: Posterior={self._bayesian_posterior:.3f}, FractalDim={self._fractal_dimension:.3f} at Tlaxcala"
            return self.emit_signal(SignalType.ALERT, self._bayesian_posterior, data=signal_data, reasoning=reasoning)
        
        if self._bayesian_posterior >= 0.5:
            reasoning = f"Bayesian resonance building: Posterior={self._bayesian_posterior:.3f}, FractalDim={self._fractal_dimension:.3f}"
            return self.emit_signal(SignalType.WATCH, self._bayesian_posterior, data=signal_data, reasoning=reasoning)

        return self.emit_signal(
            SignalType.NEUTRAL, 0.2,
            data=signal_data,
            reasoning="Fractal-Bayesian state stable (no collapse)"
        )

    def health_check(self) -> bool:
        return self._data_vector is not None

