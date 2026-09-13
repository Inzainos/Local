"""
Delta Enriched — Paquete SNT Delta para Sentinel Omega
======================================================
Encapsula la correlación cruzada geofísica ↔ financiera que vivía en
staging/snt_delta/. Provee:

  - delta_engine  : adapter DeltaSignal / analyze_pair → SatellizationEngine
  - market_mapping: constantes de tickers (crypto/bolsa)
  - fetchers      : fetch_all() — precios, clima espacial, Schumann, Trends
  - cross         : compute_cross() — correlación cruzada con lag scan
  - composite     : run_composite() — señal compuesta enriquecida

Uso típico (desde data_pipeline.py):
    from sentinel_omega.core.delta_enriched.fetchers import fetch_all
    from sentinel_omega.core.delta_enriched.composite import run_composite
    data = fetch_all(days=14)
    signal = run_composite(data)
"""

from .delta_engine import DeltaSignal, analyze_pair
from .market_mapping import CRYPTO_TICKERS, EQUITY_TICKERS, ALL_TICKERS
from .fetchers import fetch_all, FetchedData
from .cross import compute_cross, CrossResult
from .composite import run_composite, DeltaCompositeSignal

__all__ = [
    "DeltaSignal",
    "analyze_pair",
    "CRYPTO_TICKERS",
    "EQUITY_TICKERS",
    "ALL_TICKERS",
    "fetch_all",
    "FetchedData",
    "compute_cross",
    "CrossResult",
    "run_composite",
    "DeltaCompositeSignal",
]
