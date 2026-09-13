"""
delta_composite.py — Enriched composite signal for Delta SNT
=============================================================
Orchestrates the full Delta pipeline and emits a single enriched signal:

    FetchedData  →  SNT pair analysis  →  Cross-correlation  →  DeltaCompositeSignal

The enriched signal extends the core DeltaSignal (which already captures
R(t)=a·t^b anomaly, regime, leapfrog, confidence) with:

  * Geophysical context  : live Kp, Bz, solar wind, Schumann SR1
  * Cross-coupling score : how tightly geophysical drivers correlate with
                           the financial signals in this window
  * Trends stress        : Google Trends composite fear index
  * Narrative            : human-readable reasoning string

Design rules
------------
1. The SNT core is ALWAYS run — it is the backbone.
2. Geophysical context is additive enrichment; absence ≠ missing signal.
3. Output confidence = f(SNT confidence, cross-coupling, data completeness).
4. This module does NOT make investment decisions — it provides a
   decision-support signal for further analysis.

Usage:
    from delta_fetchers import fetch_all
    from delta_composite import run_composite

    data = fetch_all(days=14)
    signal = run_composite(data)
    print(signal.summary())
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np

from sentinel_omega.core.delta_enriched.delta_engine import DeltaSignal, analyze_pair
from sentinel_omega.core.delta_enriched.cross import CrossResult, compute_cross
from sentinel_omega.core.delta_enriched.market_mapping import CRYPTO_TICKERS as _CRYPTO_MKTS  # noqa: F401 (for reference)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default hub/shadow pairs to analyse
# ---------------------------------------------------------------------------

DEFAULT_CRYPTO_PAIRS = [
    ("BTC-USD", "ETH-USD"),
    ("BTC-USD", "SOL-USD"),
    ("BTC-USD", "BNB-USD"),
]

DEFAULT_EQUITY_PAIRS = [
    ("SPY", "QQQ"),    # S&P500 vs Nasdaq (tech dominance)
    ("SPY", "GLD"),    # Equities vs Gold (risk-on/off)
    ("SPY", "TLT"),    # Equities vs Long Bonds (rate sensitivity)
    ("SPY", "XLE"),    # Index vs Energy sector
    ("SPY", "XLK"),    # Index vs Tech sector
]


# ---------------------------------------------------------------------------
# Enriched signal container
# ---------------------------------------------------------------------------

@dataclass
class GeophysicalContext:
    kp_max_3d: Optional[float] = None       # max Kp last 3 days
    kp_mean_7d: Optional[float] = None      # mean Kp last 7 days
    bz_min_3d: Optional[float] = None       # most southward Bz last 3 days
    solar_wind_speed_mean: Optional[float] = None
    schumann_freq_hz: Optional[float] = None    # latest SR1 frequency
    schumann_freq_deviation: Optional[float] = None  # deviation from 7.83 Hz
    schumann_amplitude: Optional[float] = None   # normalised amplitude
    storm_active: bool = False              # Kp >= 5
    schumann_anomaly: bool = False          # |freq_dev| > 0.15 Hz

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeltaCompositeSignal:
    """
    The enriched Delta SNT output signal.

    Fields
    ------
    generated_at      : ISO UTC timestamp
    window_days       : analysis window in days
    crypto_signals    : DeltaSignal for each crypto hub/shadow pair
    equity_signals    : DeltaSignal for each equity hub/shadow pair
    cross             : CrossResult (geophysical ↔ financial correlations)
    geophysical       : GeophysicalContext (latest space-wx / Schumann snapshot)
    trends_stress     : Google Trends composite fear score (0–100)
    dominant_crypto   : the crypto pair with highest |anomaly_score|
    dominant_equity   : the equity pair with highest |anomaly_score|
    composite_score   : 0..1 overall enriched risk signal
    confidence        : 0..1 (data completeness × SNT signal quality)
    regime_label      : human-readable label (e.g. "BTC_DOMINANCE + GEOSTORM")
    narrative         : plain-text reasoning for this signal
    data_completeness : fraction of data sources that returned valid data (0..1)
    """
    generated_at: str
    window_days: int

    crypto_signals: List[DeltaSignal] = field(default_factory=list)
    equity_signals: List[DeltaSignal] = field(default_factory=list)
    cross: Optional[CrossResult] = None
    geophysical: Optional[GeophysicalContext] = None
    trends_stress: Optional[float] = None

    dominant_crypto: Optional[DeltaSignal] = None
    dominant_equity: Optional[DeltaSignal] = None

    composite_score: float = 0.0
    confidence: float = 0.0
    regime_label: str = "UNKNOWN"
    narrative: str = ""
    data_completeness: float = 0.0

    def summary(self) -> str:
        lines = [
            f"{'='*60}",
            f"  Delta SNT — Composite Signal  [{self.generated_at[:16]}Z]",
            f"  Window: {self.window_days}d  |  Completeness: {self.data_completeness:.0%}",
            f"{'='*60}",
            f"  Score     : {self.composite_score:.3f}",
            f"  Confidence: {self.confidence:.3f}",
            f"  Regime    : {self.regime_label}",
            "",
        ]
        if self.dominant_crypto:
            dc = self.dominant_crypto
            lines.append(
                f"  Crypto  [{dc.hub}/{dc.shadow}] "
                f"b={dc.b:+.3f}  regime={dc.regime}  "
                f"dir={dc.direction}  conf={dc.confidence:.2f}"
            )
        if self.dominant_equity:
            de = self.dominant_equity
            lines.append(
                f"  Equity  [{de.hub}/{de.shadow}] "
                f"b={de.b:+.3f}  regime={de.regime}  "
                f"dir={de.direction}  conf={de.confidence:.2f}"
            )
        if self.cross:
            lines.append("")
            lines.append(f"  Geo coupling  : {self.cross.composite_coupling:.3f}")
            if self.cross.dominant_driver:
                lines.append(
                    f"  Dominant link : {self.cross.dominant_driver} → "
                    f"{self.cross.dominant_target}  "
                    f"r={self.cross.dominant_r:+.3f}  lag={self.cross.dominant_lag}d"
                )
        if self.geophysical:
            g = self.geophysical
            lines.append("")
            if g.kp_max_3d is not None:
                lines.append(f"  Kp max (3d)   : {g.kp_max_3d:.1f}  storm={g.storm_active}")
            if g.schumann_freq_hz is not None:
                lines.append(
                    f"  Schumann SR1  : {g.schumann_freq_hz:.3f} Hz  "
                    f"(Δ{g.schumann_freq_deviation:+.3f})  anomaly={g.schumann_anomaly}"
                )
        if self.trends_stress is not None:
            lines.append(f"  Trends stress : {self.trends_stress:.1f}/100")
        lines.append("")
        lines.append(f"  {self.narrative}")
        lines.append(f"{'='*60}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_snt_pairs(
    prices,
    pairs: List[tuple],
    market: str,
    window: int,
) -> List[DeltaSignal]:
    """Run analyze_pair for each (hub, shadow) pair in prices."""
    if prices is None:
        return []
    results = []
    c = prices.closes
    for hub, shadow in pairs:
        if hub not in c or shadow not in c:
            continue
        h = c[hub][-window:]
        s = c[shadow][-window:]
        n = min(len(h), len(s))
        if n < 3:
            continue
        try:
            sig = analyze_pair(h[:n], s[:n], hub=hub, shadow=shadow, market=market)
            results.append(sig)
        except Exception as exc:
            logger.warning("analyze_pair(%s/%s) failed: %s", hub, shadow, exc)
    return results


def _extract_geo_context(data) -> Optional[GeophysicalContext]:
    sw = data.space_weather
    sch = data.schumann
    if sw is None and sch is None:
        return None

    ctx = GeophysicalContext()

    if sw is not None and len(sw.kp_max) >= 3:
        ctx.kp_max_3d = float(np.nanmax(sw.kp_max[-3:]))
        ctx.kp_mean_7d = float(np.nanmean(sw.kp_max[-7:])) if len(sw.kp_max) >= 7 else None
        ctx.storm_active = bool(ctx.kp_max_3d >= 5.0)
        if len(sw.bz_min) >= 3:
            ctx.bz_min_3d = float(np.nanmin(sw.bz_min[-3:]))
        if len(sw.solar_wind_speed) >= 1:
            ctx.solar_wind_speed_mean = float(np.nanmean(sw.solar_wind_speed[-7:]))

    if sch is not None and len(sch.freq_hz) >= 1:
        ctx.schumann_freq_hz = float(sch.freq_hz[-1])
        ctx.schumann_freq_deviation = float(sch.freq_deviation[-1])
        ctx.schumann_amplitude = float(sch.amplitude[-1])
        ctx.schumann_anomaly = bool(abs(ctx.schumann_freq_deviation) > 0.15)

    return ctx


def _compute_score(
    crypto_signals: List[DeltaSignal],
    equity_signals: List[DeltaSignal],
    cross: Optional[CrossResult],
    geo: Optional[GeophysicalContext],
    trends_stress: Optional[float],
) -> "Tuple[float, float]":
    """Return (composite_score, confidence) in [0,1]."""
    score = 0.0
    conf_parts: List[float] = []

    # SNT anomaly contribution
    all_snt = crypto_signals + equity_signals
    if all_snt:
        anomaly_scores = [s.anomaly_score for s in all_snt if np.isfinite(s.anomaly_score)]
        snt_confs = [s.confidence for s in all_snt if np.isfinite(s.confidence)]
        if anomaly_scores:
            score += 0.40 * min(np.mean(anomaly_scores), 1.0)
        if snt_confs:
            conf_parts.append(float(np.mean(snt_confs)))

    # Cross-coupling contribution
    if cross is not None and cross.composite_coupling > 0:
        score += 0.30 * cross.composite_coupling
        conf_parts.append(cross.composite_coupling)

    # Geomagnetic stress contribution
    if geo is not None:
        geo_stress = 0.0
        if geo.storm_active:
            geo_stress += 0.5
        if geo.kp_mean_7d is not None:
            geo_stress += min(geo.kp_mean_7d / 9.0, 0.3)
        if geo.schumann_anomaly:
            geo_stress += 0.2
        score += 0.15 * min(geo_stress, 1.0)
        conf_parts.append(0.7 if geo.storm_active or geo.schumann_anomaly else 0.4)

    # Trends stress contribution
    if trends_stress is not None:
        score += 0.15 * (trends_stress / 100.0)
        conf_parts.append(0.6)

    confidence = float(np.mean(conf_parts)) if conf_parts else 0.3
    return round(min(score, 1.0), 4), round(min(confidence, 1.0), 4)


def _regime_label(
    dominant_crypto: Optional[DeltaSignal],
    dominant_equity: Optional[DeltaSignal],
    geo: Optional[GeophysicalContext],
) -> str:
    parts: List[str] = []
    if dominant_crypto:
        if dominant_crypto.direction == "shadow_leapfrog":
            parts.append("ALT_SEASON")
        elif dominant_crypto.direction == "hub_dominates":
            parts.append("BTC_DOMINANCE")
    if dominant_equity:
        if dominant_equity.direction == "shadow_leapfrog":
            parts.append("SECTOR_BREAKOUT")
        elif dominant_equity.b < -0.1:
            parts.append("INDEX_LAG")
    if geo:
        if geo.storm_active:
            parts.append("GEOSTORM")
        if geo.schumann_anomaly:
            parts.append("SCHUMANN_SHIFT")
    return " + ".join(parts) if parts else "EQUILIBRIUM"


def _build_narrative(
    dominant_crypto: Optional[DeltaSignal],
    dominant_equity: Optional[DeltaSignal],
    cross: Optional[CrossResult],
    geo: Optional[GeophysicalContext],
    trends_stress: Optional[float],
    composite_score: float,
) -> str:
    parts: List[str] = []

    if dominant_crypto:
        dc = dominant_crypto
        parts.append(
            f"{dc.hub}/{dc.shadow} crypto pair shows b={dc.b:+.3f} "
            f"({dc.regime}, {dc.direction})"
        )
    if dominant_equity:
        de = dominant_equity
        parts.append(
            f"{de.hub}/{de.shadow} equity pair shows b={de.b:+.3f} "
            f"({de.regime}, {de.direction})"
        )
    if geo:
        if geo.storm_active:
            parts.append(
                f"Geomagnetic storm active (Kp_max_3d={geo.kp_max_3d:.1f})"
            )
        if geo.schumann_anomaly:
            parts.append(
                f"Schumann SR1 anomaly: {geo.schumann_freq_hz:.3f} Hz "
                f"(Δ{geo.schumann_freq_deviation:+.3f} from baseline)"
            )
    if cross and cross.dominant_driver and abs(cross.dominant_r) > 0.4:
        parts.append(
            f"Strong geophysical coupling: {cross.dominant_driver} → "
            f"{cross.dominant_target} (r={cross.dominant_r:+.3f}, "
            f"lag={cross.dominant_lag}d)"
        )
    if trends_stress is not None and trends_stress > 60:
        parts.append(f"Elevated market fear sentiment (Trends={trends_stress:.0f}/100)")

    if not parts:
        return "All signals within normal bounds; no notable anomaly detected."

    intensity = "elevated" if composite_score > 0.5 else "moderate" if composite_score > 0.3 else "low"
    return f"[{intensity.upper()} signal] " + ". ".join(parts) + "."


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_composite(
    data,
    window_days: int = 14,
    crypto_pairs: Optional[List[tuple]] = None,
    equity_pairs: Optional[List[tuple]] = None,
) -> DeltaCompositeSignal:
    """
    Run the full enriched Delta pipeline on `data` (a FetchedData instance).

    Parameters
    ----------
    data         : FetchedData from delta_fetchers.fetch_all()
    window_days  : analysis window in days (default 14)
    crypto_pairs : override default crypto hub/shadow pairs
    equity_pairs : override default equity hub/shadow pairs
    """
    cp = crypto_pairs or DEFAULT_CRYPTO_PAIRS
    ep = equity_pairs or DEFAULT_EQUITY_PAIRS

    # 1 — SNT pair analysis
    crypto_signals = _run_snt_pairs(data.prices, cp, "crypto", window_days)
    equity_signals = _run_snt_pairs(data.prices, ep, "stock_market", window_days)

    # 2 — Cross-correlation
    cross = compute_cross(data, window_days=window_days)

    # 3 — Geophysical context
    geo = _extract_geo_context(data)

    # 4 — Trends stress (last available value)
    trends_stress: Optional[float] = None
    if data.trends is not None and len(data.trends.composite_stress) > 0:
        trends_stress = float(np.nanmean(data.trends.composite_stress[-3:]))

    # 5 — Dominant pairs (highest anomaly)
    dominant_crypto: Optional[DeltaSignal] = None
    dominant_equity: Optional[DeltaSignal] = None
    if crypto_signals:
        dominant_crypto = max(crypto_signals, key=lambda s: abs(s.anomaly_score))
    if equity_signals:
        dominant_equity = max(equity_signals, key=lambda s: abs(s.anomaly_score))

    # 6 — Composite score & confidence
    composite_score, confidence = _compute_score(
        crypto_signals, equity_signals, cross, geo, trends_stress
    )

    # 7 — Data completeness
    sources = [data.prices, data.space_weather, data.schumann, data.trends]
    data_completeness = sum(1 for s in sources if s is not None) / len(sources)

    # Adjust confidence by completeness
    confidence = round(confidence * (0.5 + 0.5 * data_completeness), 4)

    # 8 — Labels & narrative
    regime_label = _regime_label(dominant_crypto, dominant_equity, geo)
    narrative = _build_narrative(
        dominant_crypto, dominant_equity, cross, geo, trends_stress, composite_score
    )

    return DeltaCompositeSignal(
        generated_at=datetime.now(timezone.utc).isoformat(),
        window_days=window_days,
        crypto_signals=crypto_signals,
        equity_signals=equity_signals,
        cross=cross,
        geophysical=geo,
        trends_stress=trends_stress,
        dominant_crypto=dominant_crypto,
        dominant_equity=dominant_equity,
        composite_score=composite_score,
        confidence=confidence,
        regime_label=regime_label,
        narrative=narrative,
        data_completeness=data_completeness,
    )


# ---------------------------------------------------------------------------
# CLI quick-run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Delta SNT composite signal")
    parser.add_argument("--days", type=int, default=14, help="Analysis window (days)")
    parser.add_argument("--geo", type=str, default="", help="Trends geo ('' = worldwide, 'US', 'MX')")
    args = parser.parse_args()

    from delta_fetchers import fetch_all

    print(f"Fetching {args.days} days of data …")
    fetched = fetch_all(days=args.days, trends_geo=args.geo)

    print(f"  Prices      : {'✓' if fetched.prices else '✗'}")
    print(f"  Space wx    : {'✓' if fetched.space_weather else '✗'}")
    print(f"  Schumann    : {'✓' if fetched.schumann else '✗'}")
    print(f"  Trends      : {'✓' if fetched.trends else '✗'}")
    print()

    signal = run_composite(fetched, window_days=args.days)
    print(signal.summary())
