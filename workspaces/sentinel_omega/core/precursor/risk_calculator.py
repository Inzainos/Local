"""
Precursor Risk Calculator — TITAN V32 Lineage

Core formula from legacy TITAN V32 (TOMSK WPC):
    fantasma = (viento * 0.02) + (abs(bz) ** 2) + (sch_wpc * 1.5)

Extended with:
    - Atmospheric pressure modifier (V32 Blue Jets correlation)
    - Kp storm-level escalation
    - LOD anomaly coupling

Variables:
    bz       — IMF Bz component (nT), southward = negative = geomagnetically active
    viento   — Solar wind proton speed (km/s)
    sch_wpc  — Schumann resonance WPC excitation (fraction, 0-1 range)
    pressure — Mean atmospheric pressure (hPa) at monitoring stations
    kp       — Planetary magnetic index (0-9)
    lod_ms   — Length-of-Day anomaly (ms)

Output: PrecursorRisk dataclass with composite risk score and component breakdown.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PrecursorRisk:
    timestamp: float
    fantasma: float
    risk_level: str
    bz_contribution: float
    wind_contribution: float
    schumann_contribution: float
    pressure_modifier: float
    kp_modifier: float
    lod_modifier: float
    components: Dict[str, float] = field(default_factory=dict)

    @property
    def is_elevated(self) -> bool:
        return self.risk_level in ("HIGH", "CRITICAL")


RISK_THRESHOLDS = {
    "LOW": 0.0,
    "MODERATE": 5.0,
    "HIGH": 15.0,
    "CRITICAL": 30.0,
}


def classify_risk(fantasma: float) -> str:
    if fantasma >= RISK_THRESHOLDS["CRITICAL"]:
        return "CRITICAL"
    elif fantasma >= RISK_THRESHOLDS["HIGH"]:
        return "HIGH"
    elif fantasma >= RISK_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    return "LOW"


def compute_fantasma(
    bz: float,
    viento: float,
    sch_wpc: float,
    pressure_hpa: float = 1013.0,
    kp: float = 0.0,
    lod_ms: float = 0.0,
) -> PrecursorRisk:
    """
    Compute precursor risk using the TITAN V32 fantasma formula.

    Core: fantasma = (viento * 0.02) + (abs(bz) ** 2) + (sch_wpc * 1.5)

    Modifiers applied post-core:
    - Low pressure (<1008 hPa) adds up to 3.0
    - Kp >= 5 (storm level) multiplies by up to 1.5×
    - LOD anomaly (>0.5 ms) adds coupling factor
    """
    bz_contribution = abs(bz) ** 2
    wind_contribution = viento * 0.02
    schumann_contribution = sch_wpc * 1.5

    fantasma = bz_contribution + wind_contribution + schumann_contribution

    pressure_modifier = 0.0
    if pressure_hpa < 1008.0:
        pressure_modifier = min(3.0, (1008.0 - pressure_hpa) / 5.0)
        fantasma += pressure_modifier

    kp_modifier = 1.0
    if kp >= 5.0:
        kp_modifier = 1.0 + (kp - 5.0) * 0.1
        fantasma *= kp_modifier

    lod_modifier = 0.0
    if abs(lod_ms) > 0.5:
        lod_modifier = min(2.0, abs(lod_ms) * 0.5)
        fantasma += lod_modifier

    risk_level = classify_risk(fantasma)

    return PrecursorRisk(
        timestamp=time.time(),
        fantasma=fantasma,
        risk_level=risk_level,
        bz_contribution=bz_contribution,
        wind_contribution=wind_contribution,
        schumann_contribution=schumann_contribution,
        pressure_modifier=pressure_modifier,
        kp_modifier=kp_modifier,
        lod_modifier=lod_modifier,
        components={
            "bz_nT": bz,
            "wind_kms": viento,
            "schumann_wpc": sch_wpc,
            "pressure_hpa": pressure_hpa,
            "kp": kp,
            "lod_ms": lod_ms,
        },
    )


def compute_risk_from_signals(
    agent_signals: List[Dict[str, Any]],
    atmospheric: Optional[Dict[str, Any]] = None,
) -> PrecursorRisk:
    """
    Extract variables from agent signal data dicts and compute fantasma.
    Used by the orchestrator to compute precursor risk from a completed cycle.
    """
    bz = 0.0
    viento = 0.0
    sch_wpc = 0.0
    kp = 0.0
    lod_ms = 0.0
    pressure_hpa = 1013.0

    for sig in agent_signals:
        data = sig if isinstance(sig, dict) else getattr(sig, "data", {})

        if "bz_mean" in data:
            bz = data["bz_mean"]
        if "plasma_speed" in data:
            viento = data["plasma_speed"]
        if "schumann_activity_pct" in data:
            sch_wpc = data["schumann_activity_pct"] / 100.0
        if "kp_mean" in data:
            kp = data["kp_mean"]
        if "lod_anomaly_ms" in data:
            lod_ms = data["lod_anomaly_ms"]

    if atmospheric:
        pressure_hpa = atmospheric.get("mean_pressure", 1013.0)

    return compute_fantasma(
        bz=bz, viento=viento, sch_wpc=sch_wpc,
        pressure_hpa=pressure_hpa, kp=kp, lod_ms=lod_ms,
    )


def format_risk_report(risk: PrecursorRisk) -> str:
    """Format risk for Telegram alert dispatch."""
    lines = [
        f"<b>PRECURSOR RISK: {risk.risk_level}</b>",
        f"Fantasma Index: <code>{risk.fantasma:.2f}</code>",
        "",
        "<b>Components:</b>",
        f"  Bz² = <code>{risk.bz_contribution:.2f}</code> (Bz={risk.components.get('bz_nT', 0):.1f} nT)",
        f"  Wind = <code>{risk.wind_contribution:.2f}</code> ({risk.components.get('wind_kms', 0):.0f} km/s)",
        f"  Schumann = <code>{risk.schumann_contribution:.2f}</code>",
        "",
        "<b>Modifiers:</b>",
        f"  Pressure = <code>+{risk.pressure_modifier:.2f}</code> ({risk.components.get('pressure_hpa', 1013):.0f} hPa)",
        f"  Kp = <code>×{risk.kp_modifier:.2f}</code> (Kp={risk.components.get('kp', 0):.1f})",
        f"  LOD = <code>+{risk.lod_modifier:.2f}</code> ({risk.components.get('lod_ms', 0):.2f} ms)",
    ]
    return "\n".join(lines)
