"""
Júpiter — Solar-storm correlation engine
=========================================
Júpiter answers one question: does **collective attention** (Google Trends) and
the **Schumann resonance** co-move with **solar storms** (NOAA space weather)?

It pulls three daily series over a common window and correlates them:

  * NOAA space weather (SOLAR STORMS ONLY): geomagnetic activity (Kp) and, when
    available, GOES X-ray flare flux.
  * Google Trends: public search interest in solar-storm terms.
  * Schumann resonance: current activity (its historical series accumulates live;
    correlation is computed only over whatever overlapping history exists).

For each pair it reports Spearman ρ (robust, monotonic) and the best **lagged**
cross-correlation (does search interest lag the storm? by how many days?).

Descriptive correlation analysis — not a precursor claim. Scope: solar storms.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Correlation:
    pair: str
    n: int
    spearman_rho: Optional[float]
    p_value: Optional[float]
    best_lag_days: int          # + => second series lags the first
    best_lag_corr: Optional[float]


@dataclass
class JupiterResult:
    window_days: int
    series_available: List[str]
    correlations: List[Correlation] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_days": self.window_days,
            "series_available": self.series_available,
            "correlations": [c.__dict__ for c in self.correlations],
            "notes": self.notes,
        }


def schumann_series_from_trend(rows: Optional[list]) -> Optional[pd.Series]:
    """
    Convert repository.schumann_trend() rows -> a daily Schumann-activity Series.

    Rows look like [{"timestamp", "schumann_hz", "schumann_activity"}, ...]. The
    live series accumulates one point per cycle; here it is collapsed to a daily
    mean so Júpiter can align it with Kp and Google Trends. Returns None if empty.
    """
    if not rows:
        return None
    df = pd.DataFrame(rows)
    if "timestamp" not in df.columns or "schumann_activity" not in df.columns:
        return None
    df = df.dropna(subset=["schumann_activity"])
    if df.empty:
        return None
    return _daily(df, "timestamp", "schumann_activity", how="mean")


def _daily(df: pd.DataFrame, time_col: str, value_col: str, how: str = "mean") -> pd.Series:
    """Collapse an irregular time series to a daily-indexed Series."""
    s = df[[time_col, value_col]].copy()
    s[time_col] = pd.to_datetime(s[time_col]).dt.tz_localize(None).dt.normalize()
    s = s.dropna(subset=[value_col])
    grouped = s.groupby(time_col)[value_col]
    daily = grouped.max() if how == "max" else grouped.mean()
    daily.index.name = "date"
    return daily


def _lagged_xcorr(a: pd.Series, b: pd.Series, max_lag: int = 7) -> Tuple[int, Optional[float]]:
    """
    Best Pearson correlation of a vs b over lags in [-max_lag, max_lag].
    Positive lag means b *follows* a by `lag` days (a today ~ b `lag` days later);
    negative lag means b leads a.
    """
    best_lag, best_corr = 0, None
    for lag in range(-max_lag, max_lag + 1):
        bb = b.shift(-lag)
        pair = pd.concat([a, bb], axis=1, sort=True).dropna()
        if len(pair) < 5:
            continue
        c = pair.iloc[:, 0].corr(pair.iloc[:, 1])
        if c is not None and not np.isnan(c) and (best_corr is None or abs(c) > abs(best_corr)):
            best_lag, best_corr = lag, float(c)
    return best_lag, best_corr


def _spearman(a: pd.Series, b: pd.Series) -> Tuple[int, Optional[float], Optional[float]]:
    pair = pd.concat([a, b], axis=1, sort=True).dropna()
    n = len(pair)
    if n < 5:
        return n, None, None
    try:
        from scipy.stats import spearmanr
        rho, p = spearmanr(pair.iloc[:, 0], pair.iloc[:, 1])
        return n, float(rho), float(p)
    except Exception:
        return n, float(pair.iloc[:, 0].corr(pair.iloc[:, 1], method="spearman")), None


def analyze(
    kp_df: Optional[pd.DataFrame] = None,
    xray_df: Optional[pd.DataFrame] = None,
    trends_df: Optional[pd.DataFrame] = None,
    schumann_series: Optional[pd.Series] = None,
    max_lag: int = 7,
) -> JupiterResult:
    """
    Correlate solar-storm activity against collective attention and Schumann.

    Inputs are the raw connector outputs (NOAA Kp / GOES X-ray DataFrames, the
    Google Trends DataFrame, and an optional daily Schumann Series). Any may be
    None; Júpiter correlates whatever overlapping daily history exists.
    """
    series: Dict[str, pd.Series] = {}
    if kp_df is not None and len(kp_df):
        series["kp"] = _daily(kp_df, "time_tag", "kp_index", how="max")
    if xray_df is not None and len(xray_df):
        series["xray"] = _daily(xray_df, "time_tag", "flux", how="max")
    if trends_df is not None and len(trends_df):
        series["trends"] = _daily(trends_df, "date", "solar_interest", how="max")
    if schumann_series is not None and len(schumann_series):
        s = schumann_series.copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        series["schumann"] = s

    result = JupiterResult(window_days=0, series_available=list(series.keys()))

    if len(series) < 2:
        result.notes.append(
            "Need at least two overlapping daily series to correlate "
            f"(have: {result.series_available or 'none'})."
        )
        return result

    all_dates = pd.concat(series.values(), axis=1, sort=True).dropna(how="all")
    result.window_days = int(len(all_dates))

    # Solar storms are the reference: correlate everything against kp (or xray).
    ref_key = "kp" if "kp" in series else "xray"
    for other in series:
        if other == ref_key:
            continue
        n, rho, p = _spearman(series[ref_key], series[other])
        lag, lag_c = _lagged_xcorr(series[ref_key], series[other], max_lag=max_lag)
        result.correlations.append(Correlation(
            pair=f"{ref_key}~{other}",
            n=n, spearman_rho=rho, p_value=p,
            best_lag_days=lag, best_lag_corr=lag_c,
        ))

    if "schumann" in series and series["schumann"].dropna().shape[0] < 5:
        result.notes.append(
            "Schumann history is short (series accumulates live); its correlation "
            "will stabilize as more cycles run."
        )
    return result
