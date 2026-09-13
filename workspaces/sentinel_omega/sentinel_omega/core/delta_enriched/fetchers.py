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
  Schumann   : Tomsk spectrogram WPC (TXT monthly feed is 404 as of 2026-09).
               Fallbacks: live WPC → tbl_schumann_vivo LOCF (non-placeholder).
               Returns None if all unavailable — never invents 7.83/0.
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

from sentinel_omega.core.delta_enriched.market_mapping import (
    CRYPTO_TICKERS,
    EQUITY_TICKERS,
    ALL_TICKERS,
)

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


def fetch_prices(days: int = 30) -> Optional[PriceSeries]:
    """Fetch daily closes via the project Yahoo HTTP client (no yfinance)."""
    from sentinel_omega.infrastructure.api.bolsa import fetch_yahoo_quote

    closes: Dict[str, np.ndarray] = {}
    dates: List[str] = []
    for ticker in ALL_TICKERS:
        try:
            df = fetch_yahoo_quote(ticker, days=days + 5)
        except Exception as exc:
            logger.warning("yahoo %s failed: %s", ticker, exc)
            continue
        if df is None or df.empty or "close" not in df.columns:
            continue
        tail = df.dropna(subset=["close"]).tail(days)
        if tail.empty:
            continue
        if not dates:
            ts = tail["timestamp"] if "timestamp" in tail.columns else tail.index
            dates = [str(getattr(d, "date", lambda: d)() if hasattr(d, "date") else d)[:10] for d in ts]
        arr = tail["close"].values.astype(float)
        if np.any(np.isfinite(arr)):
            closes[ticker] = arr
    if not closes:
        return None
    n = min(len(v) for v in closes.values())
    closes = {k: v[-n:] for k, v in closes.items()}
    dates = dates[-n:] if dates else [""] * n
    return PriceSeries(tickers=list(closes.keys()), dates=dates, closes=closes)


# ---------------------------------------------------------------------------
# Space weather — NOAA SWPC
# ---------------------------------------------------------------------------

def _parse_ts(ts: str):
    """Parse NOAA/Tomsk timestamps into timezone-aware UTC datetimes."""
    if not ts:
        return None
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # e.g. "2026-09-10 18:25:00"
        try:
            dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


_SWPC_KP_URL = (
    "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
)
_SWPC_SOLAR_WIND_URL = (
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json"
)
_SWPC_MAG_URL = (
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json"
)
_SWPC_PROTON_URLS = (
    "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-plot-6-hour.json",
    "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-1-day.json",
)


def _get_json(url: str, timeout: int = 30):
    import urllib.request, json
    req = urllib.request.Request(url, headers={"User-Agent": "SentinelOmega/2.5"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_space_weather(days: int = 30) -> Optional[SpaceWeather]:
    """Fetch and aggregate Kp, solar wind, IMF Bz, and proton flux from NOAA SWPC.

    2026-09-10 fixes:
      - Parse naive NOAA timestamps as UTC (was TypeError → silent empty).
      - Bz comes from rtsw_mag_1m (not wind).
      - Proton JSON is list[dict] with flux/energy keys (not [ts,val] pairs).
    """
    from collections import defaultdict

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    kp_by_day: Dict[str, list] = defaultdict(list)
    try:
        kp_data = _get_json(_SWPC_KP_URL)
        for row in kp_data:
            ts = row.get("time_tag", "")
            val = row.get("kp_index", row.get("estimated_kp", row.get("kp")))
            dt = _parse_ts(ts)
            if dt is None or dt < cutoff or val is None:
                continue
            try:
                # kp may be "0Z" string — prefer numeric fields
                if isinstance(val, str):
                    val = "".join(ch for ch in val if ch.isdigit() or ch == ".") or val
                kp_by_day[dt.strftime("%Y-%m-%d")].append(float(val))
            except (TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("NOAA Kp fetch failed: %s", exc)

    wind_speed_by_day: Dict[str, list] = defaultdict(list)
    wind_density_by_day: Dict[str, list] = defaultdict(list)
    try:
        wind_data = _get_json(_SWPC_SOLAR_WIND_URL)
        for row in wind_data:
            dt = _parse_ts(row.get("time_tag", ""))
            if dt is None or dt < cutoff:
                continue
            day = dt.strftime("%Y-%m-%d")
            speed = row.get("proton_speed")
            density = row.get("proton_density")
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
    except Exception as exc:
        logger.warning("NOAA solar wind fetch failed: %s", exc)

    bz_by_day: Dict[str, list] = defaultdict(list)
    try:
        mag_data = _get_json(_SWPC_MAG_URL)
        for row in mag_data:
            dt = _parse_ts(row.get("time_tag", ""))
            if dt is None or dt < cutoff:
                continue
            bz = row.get("bz_gsm", row.get("bz"))
            if bz is None:
                continue
            try:
                bz_by_day[dt.strftime("%Y-%m-%d")].append(float(bz))
            except (TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("NOAA MAG/Bz fetch failed: %s", exc)

    # Supplement with 7-day product feeds (array-of-arrays) for longer windows
    try:
        plasma7 = _get_json("https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json")
        # header then rows: [time, density, speed, temperature]
        for row in plasma7[1:] if isinstance(plasma7, list) and plasma7 and isinstance(plasma7[0], list) else []:
            if not row or len(row) < 3:
                continue
            dt = _parse_ts(str(row[0]))
            if dt is None or dt < cutoff:
                continue
            day = dt.strftime("%Y-%m-%d")
            try:
                if row[2] not in (None, ""):
                    wind_speed_by_day[day].append(float(row[2]))
                if row[1] not in (None, ""):
                    wind_density_by_day[day].append(float(row[1]))
            except (TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("NOAA plasma-7-day failed: %s", exc)
    try:
        mag7 = _get_json("https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json")
        # header then rows: [time, bx, by, bz, ...]  (bz often index 3)
        for row in mag7[1:] if isinstance(mag7, list) and mag7 and isinstance(mag7[0], list) else []:
            if not row or len(row) < 4:
                continue
            dt = _parse_ts(str(row[0]))
            if dt is None or dt < cutoff:
                continue
            try:
                bz_by_day[dt.strftime("%Y-%m-%d")].append(float(row[3]))
            except (TypeError, ValueError):
                pass
    except Exception as exc:
        logger.warning("NOAA mag-7-day failed: %s", exc)

    proton_by_day: Dict[str, list] = defaultdict(list)
    for url in _SWPC_PROTON_URLS:
        try:
            proton_data = _get_json(url)
            for row in proton_data:
                if isinstance(row, dict):
                    ts = row.get("time_tag", "")
                    energy = str(row.get("energy", ""))
                    # Prefer >=10 MeV channel when present
                    if energy and "10" not in energy and ">=" in energy and "1 MeV" in energy:
                        # keep 1 MeV as fallback only if no 10 MeV later
                        pass
                    val = row.get("flux", row.get("value"))
                    if energy and ">=10" not in energy.replace(" ", "") and "10 MeV" not in energy:
                        # skip non-10MeV when energy annotated
                        if "MeV" in energy and "10" not in energy:
                            continue
                elif isinstance(row, (list, tuple)) and len(row) > 1:
                    ts, val = row[0], row[1]
                else:
                    continue
                dt = _parse_ts(str(ts))
                if dt is None or dt < cutoff or val is None:
                    continue
                try:
                    proton_by_day[dt.strftime("%Y-%m-%d")].append(float(val))
                except (TypeError, ValueError):
                    pass
            if proton_by_day:
                break
        except Exception as exc:
            logger.warning("NOAA proton flux fetch failed (%s): %s", url, exc)

    all_days = sorted(
        set(kp_by_day) | set(wind_speed_by_day) | set(bz_by_day) | set(proton_by_day)
    )
    if not all_days:
        logger.warning("NOAA space weather: no days after parse (check timezone handling)")
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


def _schumann_from_wpc() -> Optional[SchumannData]:
    """Single-day series from live Tomsk spectrogram WPC (TXT feed is 404)."""
    try:
        from sentinel_omega.infrastructure.api.schumann import fetch_schumann_resonance
    except Exception:
        try:
            from infrastructure.api.schumann import fetch_schumann_resonance
        except Exception as exc:
            logger.warning("Schumann WPC import failed: %s", exc)
            return None
    try:
        result = fetch_schumann_resonance(cleanup=True)
    except Exception as exc:
        logger.warning("Schumann WPC fetch failed: %s", exc)
        return None
    if not result:
        return None
    hz, act = result
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Map activity% → relative amplitude around 1.0
    amp = max(0.05, float(act) / 100.0)
    freq = float(hz)
    return SchumannData(
        dates=[day],
        freq_hz=np.array([freq], dtype=float),
        amplitude=np.array([amp], dtype=float),
        freq_deviation=np.array([freq - _SR1_BASELINE_HZ], dtype=float),
    )


def _schumann_from_db(days: int) -> Optional[SchumannData]:
    """LOCF from tbl_schumann_vivo excluding historical 7.83/0 placeholders."""
    import sqlite3
    from pathlib import Path as _P
    candidates = [
        _P("/home/deamon/workspaces/sentinel_omega/data/SENTINEL_OMEGA_PRO.db"),
        _P(__file__).resolve().parents[2] / "data" / "SENTINEL_OMEGA_PRO.db",
    ]
    db = next((p for p in candidates if p.exists()), None)
    if db is None:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT substr(timestamp_blk,1,10) AS d, AVG(schumann_hz), AVG(schumann_activity) "
            "FROM tbl_schumann_vivo "
            "WHERE substr(timestamp_blk,1,10) >= ? "
            "  AND NOT (ABS(schumann_hz-7.83)<1e-9 AND schumann_activity=0) "
            "GROUP BY d ORDER BY d",
            (cutoff,),
        ).fetchall()
        con.close()
    except Exception as exc:
        logger.warning("Schumann DB LOCF failed: %s", exc)
        return None
    if not rows:
        return None
    dates = [r[0] for r in rows]
    freqs = np.array([float(r[1]) for r in rows], dtype=float)
    amps = np.array([max(0.05, float(r[2]) / 100.0) for r in rows], dtype=float)
    return SchumannData(
        dates=dates,
        freq_hz=freqs,
        amplitude=amps,
        freq_deviation=freqs - _SR1_BASELINE_HZ,
    )


def fetch_schumann(days: int = 30) -> Optional[SchumannData]:
    """
    Fetch Schumann resonance SR1 data.
    Order: Tomsk monthly TXT (legacy) → live WPC spectrogram → DB vivo LOCF.
    Returns None on total failure (never invents 7.83/0 series).
    """
    import ssl
    import urllib.request

    end = datetime.now(timezone.utc)
    months_to_try = set()
    for delta_days in range(days + 31):
        d = end - timedelta(days=delta_days)
        months_to_try.add(d.strftime("%Y%m"))   # 202609
        months_to_try.add(d.strftime("%y%m"))   # 2609

    raw_rows: List[tuple] = []
    ctx = ssl._create_unverified_context()
    for ym in sorted(months_to_try):
        for scheme in ("http", "https"):
            url = f"{scheme}://sosrff.tsu.ru/new/shf{ym}.txt"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "SentinelOmega/2.5"})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    for line in resp.read().decode("utf-8", errors="replace").splitlines():
                        parts = line.split()
                        if len(parts) >= 6:
                            try:
                                yr, mo, dy = int(parts[0]), int(parts[1]), int(parts[2])
                                freq = float(parts[4])
                                amp = float(parts[5])
                                raw_rows.append((f"{yr:04d}-{mo:02d}-{dy:02d}", freq, amp))
                            except (ValueError, IndexError):
                                continue
                if raw_rows:
                    break
            except Exception:
                continue
        if raw_rows:
            break

    if raw_rows:
        from collections import defaultdict
        freq_by_day: Dict[str, list] = defaultdict(list)
        amp_by_day: Dict[str, list] = defaultdict(list)
        cutoff_str = (end - timedelta(days=days)).strftime("%Y-%m-%d")
        for day, freq, amp in raw_rows:
            if day >= cutoff_str and np.isfinite(freq) and np.isfinite(amp):
                freq_by_day[day].append(freq)
                amp_by_day[day].append(amp)
        sorted_days = sorted(freq_by_day.keys())
        if sorted_days:
            freq_arr = np.array([np.mean(freq_by_day[d]) for d in sorted_days])
            amp_arr = np.array([np.mean(amp_by_day[d]) for d in sorted_days])
            amp_norm = amp_arr / amp_arr[0] if amp_arr[0] != 0 else amp_arr
            return SchumannData(
                dates=sorted_days,
                freq_hz=freq_arr,
                amplitude=amp_norm,
                freq_deviation=freq_arr - _SR1_BASELINE_HZ,
            )

    logger.warning("Tomsk Schumann TXT unavailable (404) — trying WPC then DB LOCF")
    wpc = _schumann_from_wpc()
    if wpc is not None:
        return wpc
    return _schumann_from_db(days)


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
