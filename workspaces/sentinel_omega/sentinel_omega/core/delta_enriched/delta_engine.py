"""
delta_engine.py — Adapter: SatellizationEngine → DeltaSignal / analyze_pair
===========================================================================
Provee la interfaz que espera delta_composite.py (DeltaSignal, analyze_pair)
envolviendo el SatellizationEngine ya presente en sentinel_omega.core.snt_engine.

DeltaSignal mapea los campos de SatellizationResult a los atributos que usan
_compute_score(), _regime_label() y _build_narrative() en composite.py:
  - b            : exponente de la ley de potencia  (R(t)=a·t^b)
  - anomaly_score: magnitud de la desviación del equilibrio, normalizada [0,1]
  - confidence   : confianza del ajuste (r² de la regresión log-log)
  - regime       : cadena descriptiva del régimen (ej. "satellization_active")
  - direction    : "hub_dominates" | "shadow_leapfrog" | "equilibrium"
  - hub / shadow : nombres de los activos analizados
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Optional

from sentinel_omega.core.snt_engine.satellization import (
    SatellizationEngine,
    DominanceRegime,
)

_ENGINE = SatellizationEngine()


@dataclass
class DeltaSignal:
    """Resultado SNT para un par hub/shadow en el dominio financiero-geofísico."""
    hub: str
    shadow: str
    market: str
    b: float                   # exponente ley de potencia
    anomaly_score: float       # magnitud de la anomalía [0, 1]
    confidence: float          # confianza del ajuste  [0, 1]
    regime: str                # descripción del régimen
    direction: str             # "hub_dominates" | "shadow_leapfrog" | "equilibrium"
    r_squared: float = 0.0
    n: int = 0


def analyze_pair(
    hub_values: np.ndarray,
    shadow_values: np.ndarray,
    hub: str = "HUB",
    shadow: str = "SHADOW",
    market: str = "unknown",
) -> DeltaSignal:
    """
    Ajusta R(t) = a·t^b sobre la serie hub/shadow y devuelve un DeltaSignal.

    Parámetros
    ----------
    hub_values    : serie de precios del activo dominante (array 1-D)
    shadow_values : serie de precios del activo satélite (array 1-D)
    hub / shadow  : nombres de los activos
    market        : "crypto" | "stock_market" | otros

    Retorna DeltaSignal con anomaly_score en [0,1]:
      b > 0.3  → anomalía alta (satellization activo)
      b < -0.1 → anomalía moderada-alta (convergencia/leapfrog)
      |b| ≤ 0.1 → equilibrio → anomaly_score bajo
    """
    hub_values = np.asarray(hub_values, dtype=float)
    shadow_values = np.asarray(shadow_values, dtype=float)

    n = min(len(hub_values), len(shadow_values))
    if n < 3:
        return DeltaSignal(
            hub=hub, shadow=shadow, market=market,
            b=0.0, anomaly_score=0.0, confidence=0.0,
            regime="insufficient_data", direction="equilibrium", n=n,
        )

    t = np.arange(1, n + 1, dtype=float)
    h = hub_values[:n]
    s = shadow_values[:n]

    try:
        result = _ENGINE.fit(t, h, s)
    except Exception:
        return DeltaSignal(
            hub=hub, shadow=shadow, market=market,
            b=0.0, anomaly_score=0.0, confidence=0.0,
            regime="fit_error", direction="equilibrium", n=n,
        )

    b = result.b
    r2 = max(0.0, result.r_squared)

    # anomaly_score: maps |b| onto [0,1] with gentle saturation at b=2
    anomaly_score = float(min(1.0, abs(b) / 2.0))

    # direction
    if b < -0.1:
        direction = "shadow_leapfrog"
    elif b > 0.1:
        direction = "hub_dominates"
    else:
        direction = "equilibrium"

    regime = result.regime.value  # string from DominanceRegime enum

    return DeltaSignal(
        hub=hub,
        shadow=shadow,
        market=market,
        b=round(b, 4),
        anomaly_score=round(anomaly_score, 4),
        confidence=round(r2, 4),
        regime=regime,
        direction=direction,
        r_squared=round(r2, 4),
        n=n,
    )
