"""
Shadow Node Theory (SNT) Core Engine v2.5.0
R(t) = a · t^b — Power Law Satellization Model
A(τ) = c · τ^Δ — Coupled Orbital Collapse (ACO)

Author: Elán Zainos Corona (Fractal Core Research)
Based on: github.com/Inzainos/The-shadow-Node-Theory
721 verified cases, 11 domains, Pearson ρ = -0.68 (p = 2.5e-97)

Components:
  - satellization: Power law fitting engine + dominance regimes
  - friction: Institutional friction calculator
  - asi: Atomic Sovereignty Index
  - nbody: N-Body topology matrix
  - corpus: 57 historical verification cases across 4 domains
"""

from .satellization import (
    SatellizationEngine,
    SatellizationResult,
    CollapseResult,
    DominanceRegime,
)
from .friction import InstitutionalFrictionCalculator, FrictionLevel, FrictionProfile
from .asi import AtomicSovereigntyIndex, ASIResult
from .nbody import NBodyMatrix, NBodyResult, NBodyNode, NodeClassification
from .corpus import SNT_CORPUS, CorpusCase, get_cases_by_domain, get_cases_by_trigger_type

__all__ = [
    "SatellizationEngine",
    "SatellizationResult",
    "CollapseResult",
    "DominanceRegime",
    "InstitutionalFrictionCalculator",
    "FrictionLevel",
    "FrictionProfile",
    "AtomicSovereigntyIndex",
    "ASIResult",
    "NBodyMatrix",
    "NBodyResult",
    "NBodyNode",
    "NodeClassification",
    "SNT_CORPUS",
    "CorpusCase",
    "get_cases_by_domain",
    "get_cases_by_trigger_type",
]
