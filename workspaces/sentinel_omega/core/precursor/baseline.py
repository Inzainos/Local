"""
Molchan Baseline — modelo nulo "alertar siempre"

Un hit-rate solo significa algo comparado contra lo que lograría una
estrategia SIN habilidad. El modelo nulo de Molchan es el peor predictor
honesto posible: alerta SIEMPRE, en cada slot de 72 h, en cada ubicación
evaluada. Su hit-rate es exactamente la tasa base de sismicidad
(la probabilidad de que caiga un evento M>=umbral dentro del radio de 5°
y la ventana de 72 h de una alerta cualquiera).

Ganancia = hit_rate_sistema / tasa_base:
  - > 1  → el sistema aporta información real sobre alertar a ciegas
  - <= 1 → el sistema NO supera al modelo nulo (fantasía de habilidad)

Misma geometría que AssertivityTracker: radio euclidiano en grados
(default 5°) y ventana de precursor de 72 h.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

DEFAULT_RADIUS_DEG = 5.0
DEFAULT_WINDOW_H = 72


def _event_epoch(event: Dict[str, Any]) -> Optional[float]:
    """Epoch en segundos del evento; acepta segundos o milisegundos USGS."""
    t = event.get("time")
    if t is None:
        return None
    try:
        t = float(t)
    except (TypeError, ValueError):
        return None
    # USGS FDSN entrega milisegundos; cualquier valor > ~year 33658 en
    # segundos es en realidad ms.
    return t / 1000.0 if t > 1e12 else t


@dataclass
class BaselineResult:
    base_rate: float                 # hit-rate del modelo nulo alertar-siempre
    system_hit_rate: float           # hit-rate real del sistema (viva)
    gain: Optional[float]            # None si la tasa base es 0 (sin eventos)
    n_cells: int                     # celdas (ubicación × slot de 72 h)
    n_cells_with_event: int          # celdas con >= 1 evento M>=umbral
    window_h: int
    radius_degrees: float

    @property
    def veredicto(self) -> str:
        if self.gain is None:
            return "SIN EVENTOS EN VENTANA — ganancia indefinida"
        if self.gain > 1.5:
            return "GANANCIA REAL sobre alertar-siempre"
        if self.gain > 1.0:
            return "ganancia marginal sobre el modelo nulo"
        return "SIN ganancia — no supera a alertar-siempre"


class AlwaysAlertBaseline:
    """Modelo nulo de Molchan: alerta siempre, en todas partes.

    base_rate() responde: si hubiéramos alertado en TODAS las ubicaciones
    evaluadas, en TODOS los slots de 72 h de la ventana, ¿qué fracción de
    esas alertas habría sido "confirmada" por un evento? Esa fracción es
    el piso que el sistema tiene que superar para reclamar habilidad.
    """

    def __init__(
        self,
        radius_degrees: float = DEFAULT_RADIUS_DEG,
        window_h: int = DEFAULT_WINDOW_H,
    ):
        self._radius = radius_degrees
        self._window_h = window_h

    def base_rate(
        self,
        locations: Sequence[Tuple[float, float]],
        events: List[Dict[str, Any]],
        window_days: int,
        min_magnitude: float = 4.5,
        now: Optional[float] = None,
    ) -> Tuple[float, int, int]:
        """(tasa_base, celdas_con_evento, celdas_totales)."""
        if not locations or window_days <= 0:
            return 0.0, 0, 0

        now = now if now is not None else time.time()
        start = now - window_days * 86400
        n_slots = max(1, int(np.ceil(window_days * 24 / self._window_h)))
        slot_s = self._window_h * 3600.0

        qualifying = []
        for e in events:
            if e.get("magnitude", 0) < min_magnitude:
                continue
            epoch = _event_epoch(e)
            lat, lon = e.get("latitude"), e.get("longitude")
            if lat is None or lon is None:
                continue
            qualifying.append((float(lat), float(lon), epoch))

        n_cells = len(locations) * n_slots
        hits = 0
        for lat0, lon0 in locations:
            for s in range(n_slots):
                s_ini = start + s * slot_s
                s_fin = s_ini + slot_s
                for elat, elon, eepoch in qualifying:
                    if eepoch is not None and not (s_ini <= eepoch < s_fin):
                        continue
                    d = np.sqrt((lat0 - elat) ** 2 + (lon0 - elon) ** 2)
                    if d <= self._radius:
                        hits += 1
                        break
        return hits / n_cells, hits, n_cells

    def evaluate(
        self,
        locations: Sequence[Tuple[float, float]],
        events: List[Dict[str, Any]],
        system_hit_rate: float,
        window_days: int,
        min_magnitude: float = 4.5,
        now: Optional[float] = None,
    ) -> BaselineResult:
        rate, cells_hit, cells = self.base_rate(
            locations, events, window_days, min_magnitude, now=now
        )
        gain = (system_hit_rate / rate) if rate > 0 else None
        return BaselineResult(
            base_rate=rate,
            system_hit_rate=system_hit_rate,
            gain=round(gain, 3) if gain is not None else None,
            n_cells=cells,
            n_cells_with_event=cells_hit,
            window_h=self._window_h,
            radius_degrees=self._radius,
        )
