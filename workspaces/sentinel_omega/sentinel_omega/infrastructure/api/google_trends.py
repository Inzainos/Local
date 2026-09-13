"""
Google Trends connector — collective attention on solar storms.

Public search interest is treated as a *collective sensor*: when a geomagnetic
storm lights up auroras, public search for "aurora" / "solar storm" spikes. This
connector fetches the daily interest series for a fixed solar-storm vocabulary so
Júpiter can correlate it against NOAA space-weather indices and Schumann.

Scope: SOLAR STORMS ONLY (per project scope). No other event types here.

Dependency: `pytrends` (unofficial Google Trends client). Search is public, no
key. Google may rate-limit (HTTP 429); on any failure we degrade to None so the
pipeline never breaks — consistent with the repo's "no synthetic data" rule.
"""

import logging
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Fixed solar-storm vocabulary (English; Trends interest is worldwide by default).
# Max 5 terms per Google Trends payload.
SOLAR_STORM_TERMS: List[str] = [
    "solar storm",
    "aurora",
    "solar flare",
    "geomagnetic storm",
    "northern lights",
]

# Spanish vocabulary (for geo="MX" and Spanish-speaking regions).
SOLAR_STORM_TERMS_ES: List[str] = [
    "tormenta solar",
    "aurora boreal",
    "llamarada solar",
    "tormenta geomagnética",
    "clima espacial",
]

# Which vocabulary to use per geo (default English/worldwide).
GEO_TERMS = {
    "": SOLAR_STORM_TERMS,
    "US": SOLAR_STORM_TERMS,
    "MX": SOLAR_STORM_TERMS_ES,
    "ES": SOLAR_STORM_TERMS_ES,
}


def terms_for_geo(geo: str) -> List[str]:
    """Pick the solar-storm vocabulary appropriate for a Trends geo."""
    return GEO_TERMS.get(geo, SOLAR_STORM_TERMS)


def fetch_solar_storm_trends(
    timeframe: str = "today 3-m",
    geo: str = "",
    terms: Optional[List[str]] = None,
) -> Optional[pd.DataFrame]:
    """
    Daily Google Trends interest for the solar-storm vocabulary.

    Returns a DataFrame with columns ['date', 'solar_interest', <per-term...>],
    where `solar_interest` is the row-wise max across terms (the strongest
    solar-storm attention signal that day). Returns None if pytrends is
    unavailable or Google rate-limits the request.
    """
    terms = terms or terms_for_geo(geo)
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload(kw_list=terms[:5], timeframe=timeframe, geo=geo)
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            logger.warning("Google Trends returned no data")
            return None

        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])

        df = df.reset_index().rename(columns={"index": "date"})
        term_cols = [c for c in df.columns if c != "date"]
        df["solar_interest"] = df[term_cols].max(axis=1)
        logger.info(
            f"Google Trends: {len(df)} daily points for {len(term_cols)} solar terms"
        )
        return df
    except ImportError:
        logger.error("pytrends not installed — Google Trends unavailable")
        return None
    except Exception as e:  # noqa: BLE001 — rate limits etc. must degrade, not crash
        logger.error(f"Google Trends fetch failed: {e}")
        return None
