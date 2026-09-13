"""
N-Body Matrix Processor
Extends binary Hub-Shadow to multi-entity systems.

Mexican National System (INEGI 2022):
- Binary model underestimates Tlaxcala gradient by 9.3×
- Power law: f(rank) = 396.8 × rank^(-0.473), R² = 0.838
- 89.2% of extraction flows toward CDMX, not nearest neighbor
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class NodeClassification:
    MACRO_HUB = 0
    SECONDARY_ATTRACTOR = 1
    BYPASS_LOGISTIC = 2
    SHADOW_NODE = 3
    EXOGENOUS = 4


@dataclass
class NBodyNode:
    name: str
    value: float
    level: int
    extraction_vector: float = 0.0
    b_to_hub: float = 0.0


@dataclass
class NBodyResult:
    power_law_a: float
    power_law_b: float
    r_squared: float
    nodes: List[NBodyNode] = field(default_factory=list)
    composite_gradient: float = 0.0


class NBodyMatrix:

    def analyze(
        self, entities: Dict[str, float], hub_name: str
    ) -> NBodyResult:
        if hub_name not in entities:
            raise ValueError(f"Hub '{hub_name}' not found in entities")

        hub_value = entities[hub_name]
        sorted_entities = sorted(entities.items(), key=lambda x: -x[1])

        ranks = np.arange(1, len(sorted_entities) + 1, dtype=float)
        values = np.array([v for _, v in sorted_entities])

        log_ranks = np.log(ranks)
        log_values = np.log(np.maximum(values, 1e-10))
        coef = np.polyfit(log_ranks, log_values, 1)
        b = coef[0]
        a = np.exp(coef[1])

        predicted = a * np.power(ranks, b)
        ss_res = np.sum((values - predicted) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        nodes = []
        for i, (name, value) in enumerate(sorted_entities):
            level = self._classify_level(value, hub_value, values)
            extraction = (hub_value - value) / hub_value if hub_value > 0 else 0
            nodes.append(NBodyNode(
                name=name, value=value, level=level,
                extraction_vector=extraction
            ))

        composite = sum(
            (hub_value - v) * (hub_value / (hub_value + v))
            for _, v in sorted_entities if _ != hub_name
        )

        return NBodyResult(
            power_law_a=a, power_law_b=b, r_squared=r_squared,
            nodes=nodes, composite_gradient=composite
        )

    def _classify_level(
        self, value: float, hub_value: float, all_values: np.ndarray
    ) -> int:
        ratio = value / hub_value if hub_value > 0 else 0
        if ratio > 0.95:
            return NodeClassification.MACRO_HUB
        elif ratio > 0.50:
            return NodeClassification.SECONDARY_ATTRACTOR
        elif ratio > 0.35:
            return NodeClassification.BYPASS_LOGISTIC
        elif ratio > 0.15:
            return NodeClassification.SHADOW_NODE
        else:
            return NodeClassification.EXOGENOUS
