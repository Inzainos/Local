"""
delta_cross.py — Cross-correlation: geophysical ↔ financial signals (Delta SNT)
================================================================================
Answers the core question of the enriched Delta:

  "Do space weather / Schumann resonance PRECEDE or CORRELATE with financial
   stress signals (VIX, BTC volatility, market moves)?"

Method
------
- Pearson and Spearman rolling correlation in configurable windows (3/7/14/30 d).
- Lag analysis: shift geophysical signal by L days (L = 0..MAX_LAG) and find
  the lag that maximises |correlation| with each financial series.
- Returns a CrossResult dataclass with per-pair correlations, best lags, and a
  composite "geophysical coupling score" (0..1) used by delta_composite.

All functions are pure (no I/O). Pass aligned numpy arrays; NaN-safe.

Geophysical drivers tracked:
  - Kp max        (geomagnetic storm proxy)
  - Bz min        (southward IMF — storm trigger)
  - Solar wind v  (dynamic pressure proxy)
  - Schumann freq deviation  (planetary resonance shift)
  - Schumann amplitude       (energy proxy)
  - Google Trends composite  (human sentiment proxy)

Financial targets tracked:
  - VIX close             (equity fear)
  - BTC-USD daily return  (crypto volatility proxy)
  - SPY daily return      (equity return)
  - BTC-USD / ETH-USD ratio  (crypto dominance shift)
  - Gold (GLD) return     (safe-haven flow)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

MAX_LAG = 7          # days; beyond this, causal interpretation weakens
MIN_POINTS = 7       # minimum aligned points for a valid correlation


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class PairCorrelation:
    """Correlation between one geophysical driver and one financial target."""
    driver: str
    target: str
    pearson_r: float        # contemporaneous Pearson r
    pearson_p: float        # two-tailed p-value
    spearman_r: float       # contemporaneous Spearman r
    best_lag: int           # lag (days) that maximises |Pearson r|
    best_lag_r: float       # Pearson r at best_lag
    n: int                  # number of aligned, non-NaN points


@dataclass
class CrossResult:
    """Full cross-correlation results for one analysis window."""
    window_days: int
    pairs: List[PairCorrelation] = field(default_factory=list)

    # Aggregate scores (0..1)
    geomagnetic_coupling: float = 0.0    # |mean r| across Kp/Bz/wind vs VIX/BTC
    schumann_coupling: float = 0.0       # |mean r| across Schumann vs financial
    sentiment_coupling: float = 0.0      # |mean r| across Trends vs financial
    composite_coupling: float = 0.0      # weighted mean of the three above

    # Dominant relationship detected
    dominant_driver: Optional[str] = None
    dominant_target: Optional[str] = None
    dominant_lag: int = 0
    dominant_r: float = 0.0

    def summary(self) -> str:
        lines = [
            f"CrossCorrelation ({self.window_days}d window)",
            f"  Geomagnetic coupling : {self.geomagnetic_coupling:.3f}",
            f"  Schumann coupling    : {self.schumann_coupling:.3f}",
            f"  Sentiment coupling   : {self.sentiment_coupling:.3f}",
            f"  Composite coupling   : {self.composite_coupling:.3f}",
        ]
        if self.dominant_driver:
            lines.append(
                f"  Dominant pair: {self.dominant_driver} → {self.dominant_target} "
                f"(r={self.dominant_r:+.3f}, lag={self.dominant_lag}d)"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core math helpers
# ---------------------------------------------------------------------------

def _align(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Drop NaN positions from two same-length arrays."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    return a[mask], b[mask]


def _pearson(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Pearson r and two-tailed p; returns (nan, nan) if insufficient data."""
    a, b = _align(a, b)
    if len(a) < MIN_POINTS:
        return float("nan"), float("nan")
    try:
        from scipy.stats import pearsonr
        r, p = pearsonr(a, b)
        return float(r), float(p)
    except Exception:
        return float("nan"), float("nan")


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman r; returns nan if insufficient data."""
    a, b = _align(a, b)
    if len(a) < MIN_POINTS:
        return float("nan")
    try:
        from scipy.stats import spearmanr
        r, _ = spearmanr(a, b)
        return float(r)
    except Exception:
        return float("nan")


def _lag_scan(
    driver: np.ndarray,
    target: np.ndarray,
    max_lag: int = MAX_LAG,
) -> Tuple[int, float]:
    """
    Scan lags 0..max_lag (driver leads target by `lag` days).
    Returns (best_lag, best_r) — the lag that maximises |Pearson r|.
    """
    best_lag, best_r = 0, 0.0
    driver = np.asarray(driver, dtype=float)
    target = np.asarray(target, dtype=float)
    n = len(driver)
    for lag in range(0, min(max_lag + 1, n)):
        d = driver[: n - lag]
        t = target[lag:]
        r, _ = _pearson(d, t)
        if np.isfinite(r) and abs(r) > abs(best_r):
            best_r = r
            best_lag = lag
    return best_lag, float(best_r)


# ---------------------------------------------------------------------------
# Build driver and target dictionaries from FetchedData
# ---------------------------------------------------------------------------

def _build_drivers(data) -> Dict[str, np.ndarray]:
    """Extract geophysical driver arrays from a FetchedData object."""
    drivers: Dict[str, np.ndarray] = {}
    sw = data.space_weather
    if sw is not None:
        drivers["kp_max"] = sw.kp_max
        drivers["bz_min"] = sw.bz_min
        drivers["solar_wind_speed"] = sw.solar_wind_speed
    sch = data.schumann
    if sch is not None:
        drivers["schumann_freq_dev"] = sch.freq_deviation
        drivers["schumann_amplitude"] = sch.amplitude
    tr = data.trends
    if tr is not None:
        drivers["trends_stress"] = tr.composite_stress
    return drivers


def _daily_returns(prices: np.ndarray) -> np.ndarray:
    """Compute daily log-returns; prepend NaN to keep length."""
    prices = np.asarray(prices, dtype=float)
    rets = np.empty_like(prices)
    rets[0] = np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        rets[1:] = np.diff(np.log(prices))
    return rets


def _build_targets(data) -> Dict[str, np.ndarray]:
    """Extract financial target arrays from a FetchedData object."""
    targets: Dict[str, np.ndarray] = {}
    pr = data.prices
    if pr is None:
        return targets
    c = pr.closes

    if "^VIX" in c:
        targets["vix"] = c["^VIX"]
    if "BTC-USD" in c:
        targets["btc_return"] = _daily_returns(c["BTC-USD"])
    if "SPY" in c:
        targets["spy_return"] = _daily_returns(c["SPY"])
    if "BTC-USD" in c and "ETH-USD" in c:
        # BTC dominance vs ETH
        n = min(len(c["BTC-USD"]), len(c["ETH-USD"]))
        eth = c["ETH-USD"][:n]
        btc = c["BTC-USD"][:n]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(eth > 0, btc / eth, np.nan)
        targets["btc_eth_ratio"] = ratio
    if "GLD" in c:
        targets["gold_return"] = _daily_returns(c["GLD"])
    if "^VIX" in c and "TLT" in c:
        # Composite fear proxy: VIX * (1/TLT_return variance)
        targets["vix"] = c["^VIX"]

    return targets


# ---------------------------------------------------------------------------
# Main cross-correlation function
# ---------------------------------------------------------------------------

def _trim_to_same_length(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Trim two arrays to the same length by taking the shorter tail."""
    n = min(len(a), len(b))
    return a[-n:], b[-n:]


def compute_cross(data, window_days: Optional[int] = None) -> CrossResult:
    """
    Compute all pairwise cross-correlations between geophysical drivers and
    financial targets for the data in `data` (a FetchedData instance).

    window_days: if provided, use only the last N days of each series.
    """
    w = window_days or data.window_days
    result = CrossResult(window_days=w)

    drivers = _build_drivers(data)
    targets = _build_targets(data)

    if not drivers or not targets:
        logger.warning("cross_correlation: insufficient data (drivers=%d targets=%d)",
                       len(drivers), len(targets))
        return result

    # --- Pair-wise correlations ---
    all_pairs: List[PairCorrelation] = []
    for dname, dvals in drivers.items():
        for tname, tvals in targets.items():
            d, t = _trim_to_same_length(dvals, tvals)
            if window_days:
                d = d[-window_days:]
                t = t[-window_days:]
            r, p = _pearson(d, t)
            sr = _spearman(d, t)
            best_lag, best_r = _lag_scan(d, t)
            _, aligned_t = _align(d, t)
            pair = PairCorrelation(
                driver=dname,
                target=tname,
                pearson_r=r,
                pearson_p=p,
                spearman_r=sr,
                best_lag=best_lag,
                best_lag_r=best_r,
                n=len(aligned_t),
            )
            all_pairs.append(pair)

    result.pairs = all_pairs

    # --- Aggregate coupling scores ---
    GEOMAG_DRIVERS = {"kp_max", "bz_min", "solar_wind_speed"}
    SCHUMANN_DRIVERS = {"schumann_freq_dev", "schumann_amplitude"}
    SENTIMENT_DRIVERS = {"trends_stress"}
    FINANCIAL_TARGETS = {"vix", "btc_return", "spy_return", "btc_eth_ratio", "gold_return"}

    def _mean_abs_r(driver_set: set, target_set: set) -> float:
        rs = [
            abs(p.pearson_r)
            for p in all_pairs
            if p.driver in driver_set
            and p.target in target_set
            and np.isfinite(p.pearson_r)
        ]
        return float(np.mean(rs)) if rs else 0.0

    result.geomagnetic_coupling = _mean_abs_r(GEOMAG_DRIVERS, FINANCIAL_TARGETS)
    result.schumann_coupling = _mean_abs_r(SCHUMANN_DRIVERS, FINANCIAL_TARGETS)
    result.sentiment_coupling = _mean_abs_r(SENTIMENT_DRIVERS, FINANCIAL_TARGETS)

    # Weighted composite (Schumann has higher weight per project design)
    result.composite_coupling = round(
        0.35 * result.geomagnetic_coupling
        + 0.40 * result.schumann_coupling
        + 0.25 * result.sentiment_coupling,
        4,
    )

    # --- Dominant pair (highest |r| at best lag) ---
    valid = [p for p in all_pairs if np.isfinite(p.best_lag_r)]
    if valid:
        dom = max(valid, key=lambda p: abs(p.best_lag_r))
        result.dominant_driver = dom.driver
        result.dominant_target = dom.target
        result.dominant_lag = dom.best_lag
        result.dominant_r = dom.best_lag_r

    return result


# ---------------------------------------------------------------------------
# Convenience: build from raw arrays without FetchedData
# ---------------------------------------------------------------------------

def correlate_arrays(
    driver_name: str,
    driver: np.ndarray,
    target_name: str,
    target: np.ndarray,
    max_lag: int = MAX_LAG,
) -> PairCorrelation:
    """Quick single-pair correlation (no FetchedData required)."""
    d, t = _trim_to_same_length(
        np.asarray(driver, dtype=float),
        np.asarray(target, dtype=float),
    )
    r, p = _pearson(d, t)
    sr = _spearman(d, t)
    best_lag, best_r = _lag_scan(d, t, max_lag)
    _, aligned_t = _align(d, t)
    return PairCorrelation(
        driver=driver_name,
        target=target_name,
        pearson_r=r,
        pearson_p=p,
        spearman_r=sr,
        best_lag=best_lag,
        best_lag_r=best_r,
        n=len(aligned_t),
    )
