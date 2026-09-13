"""
Muro de los Cinco Eventos — Cross-Correlation Precursor Framework

Five walls of correlated signals that, when aligned, indicate elevated
natural event probability. Each wall draws from different data domains:

  Wall 1 — GEOFÍSICO: Earthquakes, volcanic, seismic clusters
  Wall 2 — ATMOSFÉRICO: Blue Jets, Sprites Rojos, Niebla Tule, pressure anomalies
  Wall 3 — OCEÁNICO: Tsunamis, maremotos, hurricane proximity
  Wall 4 — SOLAR/GEOMAGNÉTICO: Tormenta solar, perturbación, Schumann, Silent Trigger
  Wall 5 — FINANCIERO/SOCIAL: Crypto fear, VIX spikes, bolsa bearish, trends

The "muro" fires when >= 3 walls are simultaneously active with correlated
precursors. The correlation score weights each wall by the confidence of
its strongest active precursor.

Legacy: TITAN V32 only had walls 1+4. V53 added atmospheric. Sentinel Omega
completes the picture with oceanic and financial correlation.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from sentinel_omega.core.precursor.precursor_types import PrecursorType

logger = logging.getLogger(__name__)


WALL_GEOFISICO = "GEOFÍSICO"
WALL_ATMOSFERICO = "ATMOSFÉRICO"
WALL_OCEANICO = "OCEÁNICO"
WALL_SOLAR = "SOLAR/GEOMAGNÉTICO"
WALL_FINANCIERO = "FINANCIERO/SOCIAL"

WALL_MEMBERS = {
    WALL_GEOFISICO: {
        PrecursorType.SEISMIC_CLUSTER,
        PrecursorType.VOLCANICO,
        PrecursorType.FANTASMA,
    },
    WALL_ATMOSFERICO: {
        PrecursorType.BLUE_JET,
        PrecursorType.SPRITE_ROJO,
        PrecursorType.NIEBLA_TULE,
    },
    WALL_OCEANICO: {
        PrecursorType.TSUNAMI,
        PrecursorType.HURACAN,
    },
    WALL_SOLAR: {
        PrecursorType.TORMENTA_SOLAR,
        PrecursorType.PERTURBACION_GEOMAGNETICA,
        PrecursorType.SCHUMANN,
        PrecursorType.SILENT_TRIGGER,
        PrecursorType.GRB,
    },
    WALL_FINANCIERO: {
        PrecursorType.CORRELACION_FINANCIERA,
    },
}


@dataclass
class WallStatus:
    name: str
    active: bool
    precursor_count: int
    max_confidence: float
    active_types: List[str] = field(default_factory=list)


@dataclass
class MuroResult:
    timestamp: float
    walls_active: int
    total_walls: int
    correlation_score: float
    muro_breach: bool
    wall_statuses: List[WallStatus] = field(default_factory=list)
    active_precursor_types: List[str] = field(default_factory=list)

    @property
    def risk_label(self) -> str:
        if self.walls_active >= 4:
            return "CRÍTICO"
        if self.walls_active >= 3:
            return "ALTO"
        if self.walls_active >= 2:
            return "MODERADO"
        if self.walls_active >= 1:
            return "BAJO"
        return "NORMAL"


class MuroCincoEventos:

    def __init__(self, min_walls_for_breach: int = 3):
        self.min_walls_for_breach = min_walls_for_breach
        self.last_result: Optional[MuroResult] = None

    def evaluate(self, detections: list) -> MuroResult:
        """Evaluate all five walls against current precursor detections."""
        detection_types: Dict[PrecursorType, float] = {}
        for d in detections:
            tipo = d.tipo
            conf = d.confidence
            if tipo not in detection_types or conf > detection_types[tipo]:
                detection_types[tipo] = conf

        wall_statuses = []
        walls_active = 0
        weighted_sum = 0.0

        for wall_name, members in WALL_MEMBERS.items():
            active_in_wall = {
                t: detection_types[t]
                for t in members
                if t in detection_types
            }

            is_active = len(active_in_wall) > 0
            max_conf = max(active_in_wall.values()) if active_in_wall else 0.0

            if is_active:
                walls_active += 1
                weighted_sum += max_conf

            wall_statuses.append(WallStatus(
                name=wall_name,
                active=is_active,
                precursor_count=len(active_in_wall),
                max_confidence=max_conf,
                active_types=[t.value for t in active_in_wall.keys()],
            ))

        total_walls = len(WALL_MEMBERS)
        correlation_score = 0.0
        if walls_active > 0:
            correlation_score = (walls_active / total_walls) * (weighted_sum / walls_active)

        muro_breach = walls_active >= self.min_walls_for_breach

        result = MuroResult(
            timestamp=time.time(),
            walls_active=walls_active,
            total_walls=total_walls,
            correlation_score=correlation_score,
            muro_breach=muro_breach,
            wall_statuses=wall_statuses,
            active_precursor_types=[t.value for t in detection_types.keys()],
        )
        self.last_result = result

        if muro_breach:
            logger.warning(
                f"MURO BREACH: {walls_active}/{total_walls} walls active "
                f"(score={correlation_score:.2f}, risk={result.risk_label})"
            )
        else:
            logger.info(
                f"Muro: {walls_active}/{total_walls} walls "
                f"(score={correlation_score:.2f})"
            )

        return result


def format_muro_report(result: MuroResult) -> str:
    """Format Muro result as HTML for Telegram dispatch."""
    status_icon = "🔴" if result.muro_breach else "🟢"

    lines = [
        f"<b>SENTINEL OMEGA — MURO DE LOS 5 EVENTOS</b>",
        f"",
        f"<b>Estado:</b> {status_icon} {result.risk_label}",
        f"<b>Muros activos:</b> {result.walls_active}/{result.total_walls}",
        f"<b>Correlación:</b> <code>{result.correlation_score:.2f}</code>",
        f"",
    ]

    for ws in result.wall_statuses:
        mark = "✅" if ws.active else "⬜"
        conf_str = f" ({ws.max_confidence:.0%})" if ws.active else ""
        lines.append(f"{mark} <b>{ws.name}</b>{conf_str}")
        if ws.active_types:
            types_str = ", ".join(ws.active_types)
            lines.append(f"    → {types_str}")

    if result.muro_breach:
        lines.append(f"")
        lines.append(f"<b>⚠️ ALERTA: Correlación multi-dominio detectada</b>")

    return "\n".join(lines)
