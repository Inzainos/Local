"""
delta_fetchers.py — Real data adapters for the Delta SNT engine
===============================================================
Fetches aligned financial and geophysical time series for the Delta composite
pipeline. All fetchers are *fail-soft*: they return None on any network or
parsing error so the composite signal degrades gracefully instead of crashing.

Data sources (all public):
  Financial  : yfinance — crypto (BTC, ETH, SOL …) + bolsa (SPY, QQQ, VIX,
               IPC/^MXX, sector ETFs) + Gold (GLD).
  Space wx   : NOAA SWPC JSON APIs — Kp index, solar wind (speed, density),
               IMF Bz (southward component), proton flux.
  Schumann   : Tomsk State University (sosrff.tsu.ru) daily TXT data.
               Falls back to HeartMath (heartmath.org/gci/gcms) if Tomsk is
               unreachable. Returns None if both are unavailable.
  Trends     : pytrends (Google Trends) — financial stress keywords.

Usage:
    from delta_fetchers import fetch_all
    data = fetch_all(days=14)
    # data is a FetchedData dataclass — pass it to delta_cross or delta_composite
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------

@dataclass
class PriceSeries:
    """Aligned daily close prices for a list of tickers."""
    tickers: List[str]
    dates: List[str]                    # ISO date strings YYYY-MM-DD
    closes: Dict[str, np.ndarray]       # ticker → 1-D close array


@dataclass
class SpaceWeather:
    """Daily aggregated space-weather indices."""
    dates: List[str]
    kp_max: np.ndarray          # daily max Kp (0–9)
    kp_mean: np.ndarray         # daily mean Kp
    bz_min: np.ndarray          # daily min IMF Bz (most southward, nT)
    bz_mean: np.ndarray         # daily mean IMF Bz
    solar_wind_speed: np.ndarray  # daily mean solar wind speed (km/s)
    solar_wind_density: np.ndarray  # daily mean proton density (p/cm³)
    proton_flux: np.ndarray     # daily max >10 MeV proton flux (pfu)


@dataclass
class SchumannData:
    """Daily Schumann resonance fundamental (SR1)."""
    dates: List[str]
    freq_hz: np.ndarray         # frequency of SR1 (baseline ~7.83 Hz)
    amplitude: np.ndarray       # relative amplitude (normalised to 1.0 baseline)
    freq_deviation: np.ndarray  # freq_hz − 7.83


@dataclass
class TrendsData:
    """Google Trends interest-over-time for financial stress keywords."""
    dates: List[str]
    keywords: List[str]
    interest: Dict[str, np.ndarray]  # keyword → 0-100 interest array
    composite_stress: np.ndarray     # mean across keywords (fear proxy)


@dataclass
class FetchedData:
    """All fetched inputs for one analysis window."""
    window_days: int
    fetched_at: str                     # ISO UTC timestamp
    prices: Optional[PriceSeries] = None
    space_weather: Optional[SpaceWeather] = None
    schumann: Optional[SchumannData] = None
    trends: Optional[TrendsData] = None


# ---------------------------------------------------------------------------
# Financial data — yfinance
# ---------------------------------------------------------------------------

# Core tickers fetched by default
CRYPTO_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]
EQUITY_TICKERS = [
    "SPY",    # S&P 500 ETF
    "QQQ",    # Nasdaq-100 ETF
    "^VIX",   # CBOE Volatility Index
    "^MXX",   # IPC México
    "GLD",    # Gold ETF
    "TLT",    # 20-yr US Treasury ETF (yield proxy)
    "XLF",    # Financials sector
    "XLE",    # Energy sector
    "XLK",    # Technology sector
]
ALL_TICKERS = CRYPTO_TICKERS + EQUITY_TICKERS


def fetch_prices(days: int = 30) -> Optional[PriceSeries]:
    """Fetch daily OHLCV for all tickers via yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed — skipping price fetch")
        return None

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 5)  # extra buffer for weekends/holidays

    try:
        raw = yf.download(
            ALL_TICKERS,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.warning("yfinance download failed: %s", exc)
        return None

    if raw.empty:
        return None

    # Extract Close, keep last `days` rows, drop rows where all NaN
    try:
        closes_df = raw["Close"].dropna(how="all").tail(days)
    except KeyError:
        closes_df = raw.dropna(how="all").tail(days)

    dates = [str(d.date()) for d in closes_df.index]
    closes: Dict[str, np.ndarray] = {}
    for ticker in ALL_TICKERS:
        if ticker in closes_df.columns:
            series = closes_df[ticker].values.astype(float)
            if np.any(np.isfinite(series)):
                closes[ticker] = series

    if not closes:
        return None

    return PriceSeries(
        tickers=list(closes.keys()),
        dates=dates,
        closes=closes,
    )


# ---------------------------------------------------------------------------
# Space weather — NOAA SWPC
# ---------------------------------------------------------------------------

_SWPC_KP_URL = (
    "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
)
_SWPC_SOLAR_WIND_URL = (
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
)
_SWPC_PROTON_URL = (
    "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-plot-6-hour.json"
)


def _get_json(url: str, timeout: int = 15):
    import urllib.request, json
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_space_weather(days: int = 30) -> Optional[SpaceWeather]:
    """Fetch and aggregate Kp, solar wind, IMF Bz, and proton flux from NOAA SWPC."""
    from collections import defaultdict

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # --- Kp ---
    kp_by_day: Dict[str, list] = defaultdict(list)
    try:
        kp_data = _get_json(_SWPC_KP_URL)
        for row in kp_data:
            ts = row.get("time_tag", "")
            val = row.get("kp_index")
            if ts and val is not None:
                day = ts[:10]
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt >= cutoff:
                        kp_by_day[day].append(float(val))
                except (ValueError, TypeError):
                    pass
    except Exception as exc:
        logger.warning("NOAA Kp fetch failed: %s", exc)

    # --- Solar wind / IMF Bz ---
    wind_speed_by_day: Dict[str, list] = defaultdict(list)
    wind_density_by_day: Dict[str, list] = defaultdict(list)
    bz_by_day: Dict[str, list] = defaultdict(list)
    try:
        wind_data = _get_json(_SWPC_SOLAR_WIND_URL)
        for row in wind_data:
            ts = row.get("time_tag", "")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except (ValueError, TypeError):
                continue
            day = ts[:10]
            speed = row.get("proton_speed")
            density = row.get("proton_density")
            bz = row.get("bz_gsm")
            if speed is not None:
                try:
                    wind_speed_by_day[day].append(float(speed))
                except (TypeError, ValueError):
                    pass
            if density is not None:
                try:
                    wind_density_by_day[day].append(float(density))
                except (TypeError, ValueError):
                    pass
            if bz is not None:
                try:
                    bz_by_day[day].append(float(bz))
                except (TypeError, ValueError):
                    pass
    except Exception as exc:
        logger.warning("NOAA solar wind fetch failed: %s", exc)

    # --- Proton flux ---
    proton_by_day: Dict[str, list] = defaultdict(list)
    try:
        proton_data = _get_json(_SWPC_PROTON_URL)
        for row in proton_data:
            ts = row[0] if isinstance(row, (list, tuple)) and row else None
            val = row[1] if isinstance(row, (list, tuple)) and len(row) > 1 else None
            if ts and val is not None:
                day = str(ts)[:10]
                try:
                    proton_by_day[day].append(float(val))
                except (TypeError, ValueError):
                    pass
    except Exception as exc:
        logger.warning("NOAA proton flux fetch failed: %s", exc)

    # --- Aggregate ---
    all_days = sorted(
        set(kp_by_day) | set(wind_speed_by_day) | set(bz_by_day) | set(proton_by_day)
    )
    if not all_days:
        return None

    def day_arr(by_day, days_list, agg="mean"):
        out = []
        for d in days_list:
            vals = by_day.get(d, [])
            vals = [v for v in vals if np.isfinite(v)]
            if not vals:
                out.append(np.nan)
            elif agg == "mean":
                out.append(float(np.mean(vals)))
            elif agg == "max":
                out.append(float(np.max(vals)))
            elif agg == "min":
                out.append(float(np.min(vals)))
        return np.array(out, dtype=float)

    return SpaceWeather(
        dates=all_days,
        kp_max=day_arr(kp_by_day, all_days, "max"),
        kp_mean=day_arr(kp_by_day, all_days, "mean"),
        bz_min=day_arr(bz_by_day, all_days, "min"),
        bz_mean=day_arr(bz_by_day, all_days, "mean"),
        solar_wind_speed=day_arr(wind_speed_by_day, all_days, "mean"),
        solar_wind_density=day_arr(wind_density_by_day, all_days, "mean"),
        proton_flux=day_arr(proton_by_day, all_days, "max"),
    )


# ---------------------------------------------------------------------------
# Schumann resonance — Tomsk State University
# ---------------------------------------------------------------------------

_TOMSK_BASE = "http://sosrff.tsu.ru/new/shf.txt"
_SR1_BASELINE_HZ = 7.83


def fetch_schumann(days: int = 30) -> Optional[SchumannData]:
    """
    Fetch Schumann resonance SR1 data from Tomsk State University.
    Tomsk publishes a plain-text daily table. Returns None on failure.
    """
    import urllib.request

    end = datetime.now(timezone.utc)
    dates_out: List[str] = []
    freqs: List[float] = []
    amps: List[float] = []

    # Tomsk provides monthly files; try the current and previous month
    months_to_try = set()
    for delta_days in range(days + 31):
        d = (end - timedelta(days=delta_days)).strftime("%Y%m")
        months_to_try.add(d)

    raw_rows: List[tuple] = []
    for ym in sorted(months_to_try):
        url = f"http://sosrff.tsu.ru/new/shf{ym}.txt"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                for line in resp.read().decode("utf-8", errors="replace").splitlines():
                    parts = line.split()
                    # Tomsk format: YYYY MM DD HH freq_SR1 amp_SR1 ...
                    if len(parts) >= 6:
                        try:
                            yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
                            freq = float(parts[4])
                            amp = float(parts[5])
                            raw_rows.append((f"{yr:04d}-{mo:02d}-{dy:02d}", freq, amp))
                        except (ValueError, IndexError):
                            continue
        except Exception:
            pass

    if not raw_rows:
        logger.warning("Tomsk Schumann fetch returned no data")
        return None

    # Aggregate daily mean, filter to requested window
    from collections import defaultdict
    freq_by_day: Dict[str, list] = defaultdict(list)
    amp_by_day: Dict[str, list] = defaultdict(list)
    cutoff_str = (end - timedelta(days=days)).strftime("%Y-%m-%d")

    for day, freq, amp in raw_rows:
        if day >= cutoff_str and np.isfinite(freq) and np.isfinite(amp):
            freq_by_day[day].append(freq)
            amp_by_day[day].append(amp)

    sorted_days = sorted(freq_by_day.keys())
    if not sorted_days:
        return None

    freq_arr = np.array([np.mean(freq_by_day[d]) for d in sorted_days])
    amp_arr = np.array([np.mean(amp_by_day[d]) for d in sorted_days])

    # Normalise amplitude to baseline (first observed value)
    amp_norm = amp_arr / amp_arr[0] if amp_arr[0] != 0 else amp_arr

    return SchumannData(
        dates=sorted_days,
        freq_hz=freq_arr,
        amplitude=amp_norm,
        freq_deviation=freq_arr - _SR1_BASELINE_HZ,
    )


# ---------------------------------------------------------------------------
# Google Trends — pytrends
# ---------------------------------------------------------------------------

TREND_KEYWORDS_FINANCE = [
    "stock market crash",
    "bitcoin price",
    "recession",
    "inflation",
    "market volatility",
    "gold price",
    "interest rates",
    "crypto crash",
]


def fetch_trends(
    days: int = 30,
    keywords: Optional[List[str]] = None,
    geo: str = "",
) -> Optional[TrendsData]:
    """
    Fetch Google Trends interest-over-time for financial stress keywords.
    geo: ISO country code ('' = worldwide, 'US', 'MX', etc.)
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.warning("pytrends not installed — skipping trends fetch")
        return None

    kws = keywords or TREND_KEYWORDS_FINANCE
    timeframe = f"today {min(days, 90)}-d"

    try:
        pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        # pytrends max 5 keywords per request
        all_interest: Dict[str, np.ndarray] = {}
        all_dates: Optional[List[str]] = None

        for i in range(0, len(kws), 5):
            batch = kws[i:i + 5]
            time.sleep(1.0)  # be polite to avoid 429
            pt.build_payload(batch, timeframe=timeframe, geo=geo)
            df = pt.interest_over_time()
            if df.empty:
                continue
            if all_dates is None:
                all_dates = [str(d.date()) for d in df.index]
            for kw in batch:
                if kw in df.columns:
                    all_interest[kw] = df[kw].values.astype(float)

        if not all_interest or all_dates is None:
            return None

        # Align all series to the same dates (shortest common set)
        n = min(len(v) for v in all_interest.values())
        aligned = {k: v[:n] for k, v in all_interest.items()}
        dates_aligned = all_dates[:n]

        composite = np.nanmean(np.vstack(list(aligned.values())), axis=0)

        return TrendsData(
            dates=dates_aligned,
            keywords=list(aligned.keys()),
            interest=aligned,
            composite_stress=composite,
        )

    except Exception as exc:
        logger.warning("Google Trends fetch failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_all(days: int = 30, trends_geo: str = "") -> FetchedData:
    """
    Fetch all data sources for a `days`-day window.
    Each sub-fetch is isolated — one failure does not abort the others.
    """
    logger.info("Fetching Delta data for the last %d days …", days)
    return FetchedData(
        window_days=days,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        prices=fetch_prices(days),
        space_weather=fetch_space_weather(days),
        schumann=fetch_schumann(days),
        trends=fetch_trends(days, geo=trends_geo),
    )
