"""
Stock market data connectors.
Yahoo Finance (public) for OHLCV, indices, and VIX.
"""

import logging
import time as _time
from typing import Dict, List, Optional

import pandas as pd
from sentinel_omega.infrastructure.api._http import get_session

logger = logging.getLogger(__name__)

TIMEOUT = 15


def fetch_yahoo_quote(
    symbol: str,
    days: int = 365,
    interval: str = "1d",
) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from Yahoo Finance for stocks/indices/ETFs."""
    now = int(_time.time())
    start = now - (days * 86400)

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={start}&period2={now}&interval={interval}"
    )
    try:
        resp = get_session().get(url, timeout=TIMEOUT, headers={"User-Agent": "SentinelOmega/2.0"})
        resp.raise_for_status()
        data = resp.json()

        result = data.get("chart", {}).get("result", [])
        if not result:
            return None

        timestamps = result[0].get("timestamp", [])
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]

        df = pd.DataFrame({
            "timestamp": pd.to_datetime(timestamps, unit="s"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume"),
        })
        df = df.dropna(subset=["close"])
        logger.info(f"Yahoo: {symbol} — {len(df)} records")
        return df
    except Exception as e:
        logger.error(f"Yahoo fetch failed for {symbol}: {e}")
    return None


def fetch_vix() -> Optional[pd.DataFrame]:
    """Fetch VIX (CBOE Volatility Index)."""
    return fetch_yahoo_quote("^VIX", days=365)


def fetch_sector_etfs(
    etfs: List[str] = None,
    days: int = 90,
) -> Dict[str, pd.DataFrame]:
    """Fetch sector ETF data for N-Body matrix analysis."""
    if etfs is None:
        etfs = ["XLK", "XLV", "XLF", "XLY", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC"]

    results = {}
    for etf in etfs:
        df = fetch_yahoo_quote(etf, days=days)
        if df is not None and len(df) > 10:
            results[etf] = df
    return results


def fetch_yield_spread() -> Optional[float]:
    """Fetch 10Y-2Y Treasury yield spread (proxy via Yahoo Finance)."""
    tnx = fetch_yahoo_quote("^TNX", days=5)
    twx = fetch_yahoo_quote("^IRX", days=5)

    if tnx is not None and twx is not None:
        try:
            y10 = tnx["close"].iloc[-1]
            y3m = twx["close"].iloc[-1]
            spread = y10 - y3m
            logger.info(f"Yield spread (10Y-3M): {spread:.2f}")
            return float(spread)
        except (IndexError, KeyError):
            pass
    return None
