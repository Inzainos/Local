"""
Institutional Friction Calculator
Core SNT finding: ρ = -0.68 (friction vs b), p = 2.5e-97, n=714

Friction-free domains: b ≈ +0.95 (gravity, free markets)
High-friction domains: b ≈ +0.09 (sovereign countries, predator-prey)
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class FrictionLevel(IntEnum):
    ZERO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    MAXIMUM = 4


@dataclass
class FrictionProfile:
    level: FrictionLevel
    score: float
    regulatory_density: float
    structural_barriers: float
    temporal_inertia: float
    domain: str
    description: Optional[str] = None


class InstitutionalFrictionCalculator:

    DOMAIN_BASELINES = {
        "gravity": FrictionLevel.ZERO,
        "digital_platform": FrictionLevel.LOW,
        "crypto": FrictionLevel.LOW,
        "stock_market": FrictionLevel.MEDIUM,
        "subnational": FrictionLevel.MEDIUM,
        "sovereign": FrictionLevel.HIGH,
        "predator_prey": FrictionLevel.HIGH,
        "geodynamic": FrictionLevel.MAXIMUM,
    }

    B_EXPECTATIONS = {
        FrictionLevel.ZERO: 0.95,
        FrictionLevel.LOW: 0.60,
        FrictionLevel.MEDIUM: 0.30,
        FrictionLevel.HIGH: 0.09,
        FrictionLevel.MAXIMUM: 0.02,
    }

    def calculate(
        self,
        regulatory_density: float,
        structural_barriers: float,
        temporal_inertia: float,
        domain: str = "unknown",
    ) -> FrictionProfile:
        score = (
            regulatory_density * 0.4
            + structural_barriers * 0.35
            + temporal_inertia * 0.25
        )

        if score < 0.1:
            level = FrictionLevel.ZERO
        elif score < 0.3:
            level = FrictionLevel.LOW
        elif score < 0.6:
            level = FrictionLevel.MEDIUM
        elif score < 0.85:
            level = FrictionLevel.HIGH
        else:
            level = FrictionLevel.MAXIMUM

        return FrictionProfile(
            level=level,
            score=score,
            regulatory_density=regulatory_density,
            structural_barriers=structural_barriers,
            temporal_inertia=temporal_inertia,
            domain=domain,
        )

    def expected_b(self, friction: FrictionProfile) -> float:
        return self.B_EXPECTATIONS.get(friction.level, 0.30)

    def anomaly_score(self, observed_b: float, friction: FrictionProfile) -> float:
        expected = self.expected_b(friction)
        return abs(observed_b - expected) / max(expected, 0.01)
