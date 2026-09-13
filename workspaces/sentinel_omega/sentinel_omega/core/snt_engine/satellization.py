"""
Shadow Node Theory — Satellization Engine
R(t) = a · t^b  (dominant / shadow ratio over time)

Classification (v2.5.0):
  b > 2.0  → Extreme satellization (no friction)
  b > 1.0  → Fast satellization (Roche radius)
  b > 0.3  → Active satellization
  b > 0.05 → Gradual satellization
  b > -0.1 → Equilibrium / steady state
  b ≤ -0.1 → Convergence / leapfrog

Algorithm: OLS on log-log space (np.polyfit), Pearson on log-log.
Matches: github.com/Inzainos/The-shadow-Node-Theory/code/snt_utils.py

Collapse extension (ACO v2.5.0):
  A(τ) = c · τ^Δ  (post-extinction absorption trajectory)
  Compared against exponential to detect catastrophic cliffs.
"""

import numpy as np
from scipy.stats import pearsonr, mannwhitneyu
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class DominanceRegime(Enum):
    CONVERGENCE = "convergence"
    EQUILIBRIUM = "equilibrium"
    SATELLIZATION_GRADUAL = "satellization_gradual"
    SATELLIZATION_ACTIVE = "satellization_active"
    ROCHE_RADIUS = "roche_radius"
    EXTREME = "extreme"
    LEAPFROG = "leapfrog"


@dataclass
class SatellizationResult:
    a: float
    b: float
    r_squared: float
    r_pearson: float
    p_value: float
    regime: DominanceRegime
    n_observations: int
    trigger_type: Optional[str] = None


@dataclass
class CollapseResult:
    delta: float
    r_squared: float
    exp_k: Optional[float]
    exp_r_squared: Optional[float]
    collapse_mode: str
    n_observations: int


class SatellizationEngine:
    """
    Core SNT fitting engine — matches the published algorithm exactly.
    Uses log-log OLS (not curve_fit) and Pearson (not Spearman).
    """

    def fit(
        self,
        t: np.ndarray,
        dominant: np.ndarray,
        shadow: np.ndarray,
        trigger_year: float = 0.0,
    ) -> SatellizationResult:
        """
        Fit R(t) = dominant/shadow = a * t^b via log-log OLS.
        Matches ajustar_ley_potencia() from snt_utils.py.
        """
        t = np.asarray(t, dtype=float)
        dominant = np.asarray(dominant, dtype=float)
        shadow = np.asarray(shadow, dtype=float)

        tiempos, ratios = [], []
        for i in range(len(t)):
            if shadow[i] > 0 and dominant[i] > 0:
                tau = abs(t[i] - trigger_year) + 1e-6 if trigger_year else t[i]
                tiempos.append(tau)
                ratios.append(dominant[i] / shadow[i])

        n = len(tiempos)
        if n < 3:
            raise ValueError(f"Insufficient data points: {n}")

        t_arr = np.array(tiempos, dtype=float)
        r_arr = np.array(ratios, dtype=float)

        log_t = np.log(t_arr)
        log_r = np.log(r_arr)
        coef = np.polyfit(log_t, log_r, 1)
        b = coef[0]
        a = np.exp(coef[1])

        r_pred = a * t_arr ** b
        ss_res = np.sum((r_arr - r_pred) ** 2)
        ss_tot = np.sum((r_arr - r_arr.mean()) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        r_pearson, p_value = pearsonr(log_t, log_r)

        regime = self._classify_regime(b)

        return SatellizationResult(
            a=round(a, 6),
            b=round(b, 4),
            r_squared=round(r_squared, 4),
            r_pearson=round(r_pearson, 4),
            p_value=round(p_value, 6),
            regime=regime,
            n_observations=n,
        )

    def fit_ratio(self, t: np.ndarray, ratio: np.ndarray) -> SatellizationResult:
        """
        Convenience method when ratio is pre-computed.
        Filters t>0 and ratio>0, then fits via log-log OLS.
        """
        t = np.asarray(t, dtype=float)
        ratio = np.asarray(ratio, dtype=float)

        mask = (t > 0) & np.isfinite(ratio) & (ratio > 0)
        t_clean = t[mask]
        r_clean = ratio[mask]

        n = len(t_clean)
        if n < 3:
            raise ValueError(f"Insufficient data points: {n}")

        log_t = np.log(t_clean)
        log_r = np.log(r_clean)
        coef = np.polyfit(log_t, log_r, 1)
        b = coef[0]
        a = np.exp(coef[1])

        r_pred = a * t_clean ** b
        ss_res = np.sum((r_clean - r_pred) ** 2)
        ss_tot = np.sum((r_clean - r_clean.mean()) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        r_pearson, p_value = pearsonr(log_t, log_r)

        return SatellizationResult(
            a=round(a, 6),
            b=round(b, 4),
            r_squared=round(r_squared, 4),
            r_pearson=round(r_pearson, 4),
            p_value=round(p_value, 6),
            regime=self._classify_regime(b),
            n_observations=n,
        )

    def _classify_regime(self, b: float) -> DominanceRegime:
        """Classification thresholds from SNT v2.5.0."""
        if b > 2.0:
            return DominanceRegime.EXTREME
        elif b > 1.0:
            return DominanceRegime.ROCHE_RADIUS
        elif b > 0.3:
            return DominanceRegime.SATELLIZATION_ACTIVE
        elif b > 0.05:
            return DominanceRegime.SATELLIZATION_GRADUAL
        elif b > -0.1:
            return DominanceRegime.EQUILIBRIUM
        else:
            return DominanceRegime.CONVERGENCE

    def detect_leapfrog(self, b_history: np.ndarray, window: int = 10) -> bool:
        if len(b_history) < window * 2:
            return False
        early = float(np.mean(b_history[:window]))
        late = float(np.mean(b_history[-window:]))
        return early > 0.1 and late < -0.05

    def compare_triggers(
        self, abrupt_bs: np.ndarray, gradual_bs: np.ndarray
    ) -> dict:
        stat, p = mannwhitneyu(abrupt_bs, gradual_bs, alternative='greater')
        grad_mean = float(np.mean(gradual_bs))
        ratio = float(np.mean(abrupt_bs)) / grad_mean if grad_mean != 0 else float('inf')
        return {
            "abrupt_mean_b": float(np.mean(abrupt_bs)),
            "gradual_mean_b": grad_mean,
            "velocity_ratio": ratio,
            "mann_whitney_U": float(stat),
            "p_value": float(p),
        }

    @staticmethod
    def fit_collapse(tau: np.ndarray, R: np.ndarray) -> CollapseResult:
        """
        Orbital Collapse Architecture (ACO v2.5.0).
        Fits A(τ) = c·τ^Δ (power law) and compares to exponential.
        If exponential fits better → catastrophic cliff.
        """
        tau = np.asarray(tau, dtype=float)
        R = np.asarray(R, dtype=float)
        ok = (tau > 0) & (R > 0)
        tau_c, R_c = tau[ok], R[ok]
        n = len(tau_c)

        delta, r2_pl = None, None
        exp_k, r2_exp = None, None

        if n >= 4:
            coef = np.polyfit(np.log(tau_c), np.log(R_c), 1)
            delta = round(coef[0], 3)
            pred = np.exp(coef[1]) * tau_c ** delta
            ss_res = np.sum((R_c - pred) ** 2)
            ss_tot = np.sum((R_c - R_c.mean()) ** 2)
            r2_pl = round(1 - ss_res / ss_tot, 3) if ss_tot > 0 else 0.0

            coef_e = np.polyfit(tau_c, np.log(R_c), 1)
            exp_k = round(coef_e[0], 4)
            pred_log = coef_e[1] + coef_e[0] * tau_c
            y = np.log(R_c)
            ss_res_e = np.sum((y - pred_log) ** 2)
            ss_tot_e = np.sum((y - y.mean()) ** 2)
            r2_exp = round(1 - ss_res_e / ss_tot_e, 3) if ss_tot_e > 0 else 0.0

        mode = _classify_collapse(delta, r2_pl, exp_k, r2_exp)

        return CollapseResult(
            delta=delta if delta is not None else 0.0,
            r_squared=r2_pl if r2_pl is not None else 0.0,
            exp_k=exp_k,
            exp_r_squared=r2_exp,
            collapse_mode=mode,
            n_observations=n,
        )


def _classify_collapse(
    delta: Optional[float],
    r2_pl: Optional[float],
    exp_k: Optional[float],
    r2_exp: Optional[float],
) -> str:
    if delta is None:
        return "insufficient_data"
    if r2_exp is not None and r2_pl is not None and r2_exp > r2_pl + 0.05:
        if exp_k is not None and exp_k < -0.1:
            return "catastrophic_cliff"
    if r2_pl is not None and r2_pl > 0.7:
        return "regulated_orbital_decay"
    if r2_pl is not None and r2_pl < 0.3:
        return "cracquelure_decay"
    return "floor_arrested"
