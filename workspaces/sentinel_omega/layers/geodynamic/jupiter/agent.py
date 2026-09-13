"""
Júpiter Agent — collective-attention corroborator for solar storms
==================================================================
The 7th geodynamic agent. Where Alfa-1/Beta-1 read the physical space weather,
Júpiter reads the **collective sensor**: it correlates solar-storm activity
(Kp / X-ray) against public search interest (Google Trends) and the Schumann
resonance, and raises a signal when that attention meaningfully co-moves with —
and is currently spiking around — real solar activity.

It emits:
  * ALERT — a geomagnetic storm is active (Kp ≥ 5) and either attention is
    spiking or the attention↔storm correlation is significant; OR the
    attention↔storm correlation is significant AND attention spikes ≥ 2σ.
  * WATCH — a storm is active, or attention spikes with a significant correlation.
  * NEUTRAL — otherwise.
  * NO_SIGNAL — no data.

Family: space_weather (corroborates Alfa-1/Alfa-2 without changing the Padre's
cross-family math). Descriptive corroboration, not a standalone precursor claim.
"""

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from sentinel_omega.core.shared.agent_base import BaseAgent, AgentSignal, SignalType
from sentinel_omega.core.precursor import jupiter


class JupiterAgent(BaseAgent):

    CORR_SIGNIF = 0.3          # |Spearman ρ| threshold for a meaningful link
    CORR_P = 0.05
    STORM_KP = 5.0            # Kp ≥ 5 = geomagnetic storm (G1+)
    ATTENTION_Z_WATCH = 1.0
    ATTENTION_Z_ALERT = 2.0

    def __init__(self):
        super().__init__(name="jupiter", layer="geodynamic")
        self._kp_df: Optional[pd.DataFrame] = None
        self._xray_df: Optional[pd.DataFrame] = None
        self._trends_df: Optional[pd.DataFrame] = None
        self._schumann_series: Optional[pd.Series] = None

    def ingest(self, data: Dict[str, Any]) -> None:
        self._kp_df = data.get("kp_df")
        self._xray_df = data.get("xray_df")
        self._trends_df = data.get("trends_df")
        self._schumann_series = data.get("schumann_series")
        self.logger.info(
            "Ingested: kp=%s trends=%s schumann=%s",
            self._kp_df is not None, self._trends_df is not None,
            self._schumann_series is not None,
        )

    @staticmethod
    def _latest_daily_kp(kp_df: Optional[pd.DataFrame]) -> Optional[float]:
        if kp_df is None or len(kp_df) == 0:
            return None
        s = kp_df.copy()
        s["d"] = pd.to_datetime(s["time_tag"]).dt.tz_localize(None).dt.normalize()
        return float(s.groupby("d")["kp_index"].max().iloc[-1])

    @staticmethod
    def _attention_z(trends_df: Optional[pd.DataFrame]) -> Optional[float]:
        if trends_df is None or "solar_interest" not in trends_df or len(trends_df) < 5:
            return None
        x = trends_df["solar_interest"].astype(float).values
        std = np.std(x)
        if std <= 1e-9:
            return 0.0
        return float((x[-1] - np.mean(x)) / std)

    def analyze(self) -> AgentSignal:
        has_data = any(v is not None and len(v) for v in (
            self._kp_df, self._trends_df, self._xray_df, self._schumann_series))
        if not has_data:
            return self.emit_signal(
                SignalType.NO_SIGNAL, 0.0, reasoning="No space-weather / attention data",
            )

        result = jupiter.analyze(
            kp_df=self._kp_df, xray_df=self._xray_df,
            trends_df=self._trends_df, schumann_series=self._schumann_series,
        )
        corr = next((c for c in result.correlations if c.pair.endswith("trends")), None)
        corr_signif = bool(
            corr and corr.spearman_rho is not None
            and abs(corr.spearman_rho) >= self.CORR_SIGNIF
            and (corr.p_value is None or corr.p_value < self.CORR_P)
        )

        latest_kp = self._latest_daily_kp(self._kp_df)
        storm_active = latest_kp is not None and latest_kp >= self.STORM_KP
        att_z = self._attention_z(self._trends_df)
        att_z = 0.0 if att_z is None else att_z

        data = {
            "correlations": result.to_dict()["correlations"],
            "latest_kp": latest_kp,
            "storm_active": storm_active,
            "attention_z": round(att_z, 3),
            "corr_significant": corr_signif,
            "series_available": result.series_available,
        }

        if (corr_signif and att_z >= self.ATTENTION_Z_ALERT) or \
           (storm_active and (corr_signif or att_z >= self.ATTENTION_Z_ALERT)):
            conf = min(0.6 + 0.1 * att_z + (0.1 if corr_signif else 0.0), 0.9)
            return self.emit_signal(
                SignalType.ALERT, conf, data=data,
                reasoning=(
                    f"Solar-storm attention signal: storm={storm_active} "
                    f"(Kp={latest_kp}), attention={att_z:.1f}σ, corr_significant={corr_signif}"
                ),
            )
        if storm_active or (corr_signif and att_z >= self.ATTENTION_Z_WATCH) or \
           att_z >= self.ATTENTION_Z_ALERT:
            return self.emit_signal(
                SignalType.WATCH, 0.45 + 0.1 * min(att_z, 2.0), data=data,
                reasoning=(
                    f"Elevated: storm={storm_active} (Kp={latest_kp}), "
                    f"attention={att_z:.1f}σ, corr_significant={corr_signif}"
                ),
            )
        return self.emit_signal(
            SignalType.NEUTRAL, 0.2, data=data,
            reasoning=(
                f"Attention within norms ({att_z:.1f}σ); "
                f"no active storm; corr_significant={corr_signif}"
            ),
        )

    def health_check(self) -> bool:
        return (self._kp_df is not None and len(self._kp_df) > 0) or \
               (self._trends_df is not None and len(self._trends_df) > 0)
