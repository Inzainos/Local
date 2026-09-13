"""
market_mapping.py — Constantes de tickers para el Delta SNT
============================================================
Centraliza las listas de activos que usan fetchers.py y composite.py.
"""

CRYPTO_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]

EQUITY_TICKERS = [
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "GLD",   # Gold ETF
    "TLT",   # Long-term Bonds
    "XLE",   # Energy sector
    "XLK",   # Tech sector
    "^VIX",  # Volatility index
    "^MXX",  # IPC México
]

ALL_TICKERS = CRYPTO_TICKERS + EQUITY_TICKERS

__all__ = ["CRYPTO_TICKERS", "EQUITY_TICKERS", "ALL_TICKERS"]
