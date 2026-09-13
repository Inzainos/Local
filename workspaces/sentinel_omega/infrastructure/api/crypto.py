"""
Crypto market data connectors.
Yahoo Finance and CoinGecko public endpoints (no key required for basic usage).
Binance public market data API.

SNT application: fits R(t) = dominant/shadow on BTC/altcoin dominance ratios
to detect satellization, convergence (alt season), and collapse precursors.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sentinel_omega.infrastructure.api._http import get_session

logger = logging.getLogger(__name__)

TIMEOUT = 15


def fetch_yahoo_chart(
    symbol: str,
    period1: int,
    period2: int,
    interval: str = "1d",
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV from Yahoo Finance chart API.
    Same source used in SNT collapse analysis (LUNA, FTX).
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={period1}&period2={period2}&interval={interval}"
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
        logger.info(f"Yahoo Finance: {symbol} — {len(df)} records")
        return df
    except Exception as e:
        logger.error(f"Yahoo Finance fetch failed for {symbol}: {e}")
    return None


def fetch_coingecko_market_chart(
    coin_id: str = "bitcoin",
    vs_currency: str = "usd",
    days: int = 365,
) -> Optional[pd.DataFrame]:
    """Fetch price history from CoinGecko (public, rate-limited)."""
    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        f"?vs_currency={vs_currency}&days={days}"
    )
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        prices = data.get("prices", [])
        if not prices:
            return None

        df = pd.DataFrame(prices, columns=["timestamp", "price"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        logger.info(f"CoinGecko: {coin_id} — {len(df)} price records")
        return df
    except Exception as e:
        logger.error(f"CoinGecko fetch failed for {coin_id}: {e}")
    return None


def fetch_coingecko_dominance() -> Optional[Dict[str, float]]:
    """Fetch BTC and ETH dominance percentages from CoinGecko."""
    url = "https://api.coingecko.com/api/v3/global"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", {}).get("market_cap_percentage", {})
        logger.info(f"CoinGecko dominance: BTC={data.get('btc', 0):.1f}%")
        return data
    except Exception as e:
        logger.error(f"CoinGecko dominance fetch failed: {e}")
    return None


def fetch_binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1d",
    limit: int = 365,
) -> Optional[pd.DataFrame]:
    """Fetch klines (OHLCV) from Binance public API."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore",
        ])
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        logger.info(f"Binance: {symbol} — {len(df)} klines")
        return df[["timestamp", "open", "high", "low", "close", "volume"]]
    except Exception as e:
        logger.error(f"Binance fetch failed for {symbol}: {e}")
    return None


def fetch_fear_greed_index() -> Optional[Dict]:
    """Fetch Crypto Fear & Greed Index (alternative.me, public)."""
    url = "https://api.alternative.me/fng/?limit=30&format=json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            latest = data[0]
            result = {
                "value": int(latest["value"]),
                "classification": latest["value_classification"],
                "timestamp": latest["timestamp"],
            }
            logger.info(f"Fear & Greed: {result['value']} ({result['classification']})")
            return result
    except Exception as e:
        logger.error(f"Fear & Greed fetch failed: {e}")
    return None


def build_dominance_ratios(
    pairs: List[str] = None,
    days: int = 365,
) -> Dict[str, pd.DataFrame]:
    """
    Build BTC/altcoin dominance ratio time series for SNT fitting.
    Returns dict of pair_name -> DataFrame with columns [timestamp, ratio].
    """
    if pairs is None:
        pairs = ["ethereum", "solana", "binancecoin", "ripple", "cardano"]

    btc_df = fetch_coingecko_market_chart("bitcoin", days=days)
    if btc_df is None:
        return {}

    results = {}
    for alt in pairs:
        alt_df = fetch_coingecko_market_chart(alt, days=days)
        if alt_df is None:
            continue

        merged = pd.merge_asof(
            btc_df.rename(columns={"price": "btc_price"}).sort_values("timestamp"),
            alt_df.rename(columns={"price": "alt_price"}).sort_values("timestamp"),
            on="timestamp",
            direction="nearest",
            tolerance=pd.Timedelta("2h"),
        )
        merged = merged.dropna()
        if len(merged) > 10:
            merged["ratio"] = merged["btc_price"] / merged["alt_price"]
            results[f"BTC/{alt.upper()}"] = merged[["timestamp", "ratio"]]
            logger.info(f"Built ratio BTC/{alt.upper()}: {len(merged)} points")

    return results
