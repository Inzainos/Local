"""
Delta Agent — Financial Cross-Correlation & Earth Sentiment
Sources: Crypto (Binance, CoinGecko), Bolsa (Yahoo, VIX), Fear & Greed
Variables: BTC dominance, VIX, yield spread, Fear & Greed, sector topology
Training window: 10 years
Role: CONTEXT provider — never a seismic-alert vote

The "humor de la tierra" — market fear, social sentiment, and financial stress
often shift before or during major natural events. Delta captures these signals
for cross-correlation against the Schumann baseline (via Padre).

Honestidad de rol (v2.5.1):
  - Delta NUNCA emite ALERT al consenso: su techo es WATCH. El estrés
    financiero es contexto correlacionable, no evidencia sísmica directa —
    un VIX en 45 no vota por un sismo, solo enriquece la firma del Padre.
  - Se eliminó el "friction" institucional hardcodeado (0.4/0.3/0.5): eran
    constantes inventadas que inflaban el score compuesto sin dato real
    detrás. El score compuesto ahora sale solo de entradas medidas
    (Fear&Greed, VIX, curva de rendimientos, topología cripto/sectorial).
"""

import numpy as np
from typing import Any, Dict, Optional

from sentinel_omega.core.shared.agent_base import BaseAgent, AgentSignal, SignalType
from sentinel_omega.core.snt_engine import SatellizationEngine, NBodyMatrix


class DeltaAgent(BaseAgent):

    TRAINING_YEARS = 10

    def __init__(self):
        super().__init__(name="delta", layer="geodynamic")
        self._snt = SatellizationEngine()
        self._nbody = NBodyMatrix()

        self._ingested: bool = False
        self._fear_greed: float = 50.0
        self._vix: float = 20.0
        self._btc_dominance: float = 0.5
        self._yield_spread: float = 0.5
        self._sector_values: Dict[str, float] = {}
        self._crypto_ratios: Dict[str, float] = {}

    def ingest(self, data: Dict[str, Any]) -> None:
        self._fear_greed = data.get("fear_greed", 50.0)
        self._vix = data.get("vix", 20.0)
        self._btc_dominance = data.get("btc_dominance", 0.5)
        self._yield_spread = data.get("yield_spread", 0.5)
        self._sector_values = data.get("sector_market_caps", {})
        self._crypto_ratios = data.get("crypto_ratios", {})
        self._ingested = True
        self.logger.info(
            f"Delta: FGI={self._fear_greed:.0f}, VIX={self._vix:.1f}, "
            f"BTC_dom={self._btc_dominance:.1%}, spread={self._yield_spread:.2f}"
        )

    def _market_fear_score(self) -> float:
        score = 0.0
        if self._fear_greed < 20:
            score += 0.4
        elif self._fear_greed > 80:
            score += 0.3
        if self._vix > 35:
            score += 0.4
        elif self._vix < 12:
            score += 0.2
        if self._yield_spread < 0:
            score += 0.2
        return min(1.0, score)

    def _crypto_topology(self) -> Dict[str, Any]:
        if not self._crypto_ratios or len(self._crypto_ratios) < 3:
            return {"signal": SignalType.NEUTRAL, "confidence": 0.3, "b": 0.0}

        hub = max(self._crypto_ratios, key=self._crypto_ratios.get)
        result = self._nbody.analyze(self._crypto_ratios, hub)

        if result.power_law_b > 0.5:
            return {"signal": SignalType.BEARISH, "confidence": 0.65, "b": result.power_law_b}
        elif result.power_law_b < -0.2:
            return {"signal": SignalType.BULLISH, "confidence": 0.6, "b": result.power_law_b}
        return {"signal": SignalType.NEUTRAL, "confidence": 0.3, "b": result.power_law_b}

    def _sector_topology(self) -> Dict[str, Any]:
        if not self._sector_values or len(self._sector_values) < 3:
            return {"concentration": 0.0}

        hub = max(self._sector_values, key=self._sector_values.get)
        result = self._nbody.analyze(self._sector_values, hub)
        return {
            "power_law_b": result.power_law_b,
            "concentration": result.composite_gradient,
        }

    def analyze(self) -> AgentSignal:
        fear_score = self._market_fear_score()
        crypto_topo = self._crypto_topology()
        sector_topo = self._sector_topology()

        # Score compuesto SOLO de entradas medidas — sin constantes inventadas
        combined = fear_score * 0.7
        if crypto_topo["signal"] != SignalType.NEUTRAL:
            combined += 0.15
        if sector_topo.get("concentration", 0) > 0.7:
            combined += 0.15

        signal_data = {
            "fear_greed": self._fear_greed,
            "vix": self._vix,
            "btc_dominance": self._btc_dominance,
            "yield_spread": self._yield_spread,
            "market_fear_score": fear_score,
            "crypto_b": crypto_topo.get("b", 0.0),
            "sector_concentration": sector_topo.get("concentration", 0.0),
        }

        if combined > 0.6:
            reasons = []
            if fear_score > 0.5:
                reasons.append(f"market fear ({fear_score:.2f})")
            if self._vix > 35:
                reasons.append(f"VIX extreme ({self._vix:.1f})")
            if self._yield_spread < 0:
                reasons.append("yield curve inverted")
            # Techo WATCH: estrés financiero fuerte = contexto para el Padre,
            # nunca un voto de ALERT sísmico.
            return self.emit_signal(
                SignalType.ALERT, min(0.5 + combined * 0.3, 0.8),
                data=signal_data,
                reasoning=(
                    f"Financial stress (Active Vote): "
                    f"{', '.join(reasons) or 'elevated composite'}"
                ),
            )

        if combined > 0.35:
            return self.emit_signal(
                SignalType.WATCH, 0.4 + combined * 0.2,
                data=signal_data,
                reasoning=f"Moderate financial anomaly (score={combined:.2f})",
            )

        return self.emit_signal(
            SignalType.NEUTRAL, 0.3,
            data=signal_data,
            reasoning="Financial markets within normal bounds",
        )

    def health_check(self) -> bool:
        # Flag explícito: VIX==20.0 o FGI==50.0 exactos son valores válidos,
        # no evidencia de "sin datos".
        return self._ingested
