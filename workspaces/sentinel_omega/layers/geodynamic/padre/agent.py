"""
Padre / Árbitro — Hierarchical Consensus Validator (v2.5.4 - Three Acts)
========================================================================
Architecture: SNT Families (Alfa/Beta/Delta) -> Omega -> Loki (Final Act)

Asymmetric Loss: missed events penalized 10x more than false alarms.
VETO power: no alert without cross-family validation.

Hierarchy:
  - Padre validates SNT Families against 30-year history
  - Omega provides spatial/cosmic corroboration
  - Loki provides Bayesian probability collapse (Final Act)

Schumann correlation:
  Everything correlates against the Schumann resonance (Beta-1).
  If Schumann is perturbed alongside any other signal, that's a precursor.

Flow:
  1. SNT Families detect patterns -> cross-family validation
  2. Omega validates spatial/cosmic correlation
  3. Loki performs Bayesian probability collapse
  4. If all three acts align -> ALERT CONFIRMED
"""

from typing import Any, Dict, List, Optional

from sentinel_omega.core.shared.agent_base import (
    PadreAgent, AgentSignal, ConsensusResult, SignalType
)


class GeodynamicPadre(PadreAgent):

    AGENT_TRAINING_YEARS = {
        "alfa1": 30, "beta1": 30,
        "alfa2": 14, "beta2": 14,
        "delta": 10,
        "jupiter": 5,
        "omega": 30,
        "loki": 0,  # Loki is not trained on history; it computes probability
    }

    FAMILY_MAP = {
        "alfa1": "space_weather",
        "alfa2": "space_weather",
        "beta1": "schumann_cymatics",
        "beta2": "schumann_cymatics",
        "delta": "financial_sentiment",
        "jupiter": "space_weather",
        "omega": "cosmic_correlation",
        "loki": "unified_field",  # Act 3 - standalone
    }

    SENIOR_AGENTS = {"alfa1", "beta1"}
    JUNIOR_AGENTS = {"alfa2", "beta2"}
    SENIOR_FOR_JUNIOR = {"alfa2": "alfa1", "beta2": "beta1"}

    PESO_DEMOTION_THRESHOLD = 0.6

    def __init__(self):
        super().__init__(name="padre_geo", domain="geodynamic")
        self.miss_penalty = 10.0
        self.false_alarm_penalty = 1.0
        self.pesos_bots: Dict[str, float] = {}
        self.asertividad_omega: float = 0.0
        self.asertividad_corum: float = 0.0
        self.omega_es_referencia: bool = False
        self.loki_probability: float = 0.0
        self.loki_threshold: float = 0.8

    def set_pesos(self, pesos: Dict[str, float]) -> None:
        self.pesos_bots = dict(pesos or {})

    def set_asertividades(self, omega: float, corum: float) -> None:
        self.asertividad_omega = float(omega or 0)
        self.asertividad_corum = float(corum or 0)
        self.omega_es_referencia = (
            self.asertividad_omega > 0
            and self.asertividad_omega >= self.asertividad_corum
        )

    def _aplicar_pesos(self, validated: Dict[str, AgentSignal]) -> Dict[str, AgentSignal]:
        if not self.pesos_bots:
            return validated
        weighted = {}
        for name, sig in validated.items():
            peso = self.pesos_bots.get(name, 1.0)
            if peso == 1.0:
                weighted[name] = sig
                continue
            signal_type = sig.signal_type
            if peso < self.PESO_DEMOTION_THRESHOLD and signal_type == SignalType.ALERT:
                signal_type = SignalType.WATCH
            weighted[name] = AgentSignal(
                agent_name=sig.agent_name,
                signal_type=signal_type,
                confidence=min(sig.confidence * peso, 0.95),
                timestamp=sig.timestamp,
                data={**sig.data, "peso_bot": peso},
                reasoning=sig.reasoning,
            )
        return weighted

    def _validate_junior_with_senior(self, signals: List[AgentSignal]) -> Dict[str, AgentSignal]:
        by_name = {s.agent_name: s for s in signals}
        validated = {}
        for senior_name in self.SENIOR_AGENTS:
            if senior_name in by_name:
                validated[senior_name] = by_name[senior_name]
        for junior_name, senior_name in self.SENIOR_FOR_JUNIOR.items():
            junior = by_name.get(junior_name)
            senior = by_name.get(senior_name)
            if junior is None:
                continue
            junior_active = junior.signal_type in (SignalType.ALERT, SignalType.WATCH)
            senior_confirms = senior is not None and senior.signal_type in (SignalType.ALERT, SignalType.WATCH)
            if junior_active and senior_confirms:
                boost = min(junior.confidence * 1.2, 0.95)
                validated[junior_name] = AgentSignal(
                    agent_name=junior_name,
                    signal_type=junior.signal_type,
                    confidence=boost,
                    timestamp=junior.timestamp,
                    data={**junior.data, "senior_confirmed": True},
                    reasoning=f"{junior.reasoning} [confirmed by {senior_name}]",
                )
            elif junior_active and not senior_confirms:
                validated[junior_name] = AgentSignal(
                    agent_name=junior_name,
                    signal_type=SignalType.WATCH,
                    confidence=junior.confidence * 0.5,
                    timestamp=junior.timestamp,
                    data={**junior.data, "senior_confirmed": False},
                    reasoning=f"{junior.reasoning} [unconfirmed by {senior_name}]",
                )
            else:
                validated[junior_name] = junior
        if "delta" in by_name:
            validated["delta"] = by_name["delta"]
        for extra in ("jupiter", "omega", "loki"):
            if extra in by_name:
                validated[extra] = by_name[extra]
        return validated

    def _cross_family_check(self, validated: Dict[str, AgentSignal]) -> Dict[str, bool]:
        family_active = {}
        for agent_name, signal in validated.items():
            family = self.FAMILY_MAP.get(agent_name, "unknown")
            is_active = signal.signal_type in (SignalType.ALERT, SignalType.WATCH)
            if family not in family_active:
                family_active[family] = False
            if is_active:
                family_active[family] = True
        return family_active

    def _schumann_correlation(self, validated: Dict[str, AgentSignal]) -> float:
        beta1 = validated.get("beta1")
        if beta1 is None:
            return 0.0
        schumann_active = beta1.signal_type in (SignalType.ALERT, SignalType.WATCH)
        if not schumann_active:
            return 0.0
        other_active = sum(1 for name, sig in validated.items() if name != "beta1" and sig.signal_type in (SignalType.ALERT, SignalType.WATCH))
        return min(1.0, other_active * 0.3 + beta1.confidence * 0.4)

    def _loki_validation(self, validated: Dict[str, AgentSignal]) -> Dict[str, Any]:
        loki_sig = validated.get("loki")
        if loki_sig is None:
            return {"loki_active": False, "loki_probability": 0.0, "loki_confirms": False, "loki_reasoning": "Loki signal not received"}
        self.loki_probability = loki_sig.confidence
        loki_confirms = loki_sig.signal_type in (SignalType.ALERT, SignalType.WATCH) and self.loki_probability >= self.loki_threshold
        return {"loki_active": True, "loki_probability": self.loki_probability, "loki_confirms": loki_confirms, "loki_reasoning": loki_sig.reasoning, "loki_signal_type": loki_sig.signal_type.value}

    def _dual_ask(self, omega_sig, corum_signal: SignalType, alert_signals, watch_signals):
        meta = {"omega_voto": None, "omega_referencia": self.omega_es_referencia, "asertividad_omega": self.asertividad_omega, "asertividad_corum": self.asertividad_corum, "dual_ask": None}
        if omega_sig is None:
            return meta
        meta["omega_voto"] = {"signal": omega_sig.signal_type.value, "confidence": omega_sig.confidence, "reasoning": (omega_sig.reasoning or "")[:300]}
        omega_alert = omega_sig.signal_type in (SignalType.ALERT, SignalType.WATCH)
        corum_alert = corum_signal in (SignalType.ALERT, SignalType.WATCH) or bool(alert_signals or watch_signals)
        if omega_alert and not corum_alert:
            meta["dual_ask"] = {"quien_primero": "omega", "pregunta_a": "corum", "texto": "Omega alerta -- que ven las familias del corum?"}
        elif corum_alert and not omega_alert:
            meta["dual_ask"] = {"quien_primero": "corum", "pregunta_a": "omega", "texto": "Corum alerta -- que ve Omega en espacial + Beta?"}
        elif omega_alert and corum_alert:
            meta["dual_ask"] = {"quien_primero": "ambos", "pregunta_a": "juez", "texto": "Alineados en alerta -- el Juez valida post-evento"}
        if self.omega_es_referencia and omega_alert:
            meta["omega_eleva_revision"] = True
        return meta

    def evaluate_consensus(self, signals: List[AgentSignal]) -> ConsensusResult:
        if not signals:
            return ConsensusResult(consensus_reached=False, final_signal=SignalType.NO_SIGNAL, confidence=0.0, agent_signals=signals, veto_active=True, veto_reason="No signals received")
        validated = self._validate_junior_with_senior(signals)
        validated = self._aplicar_pesos(validated)
        omega_sig = None
        loki_sig = None
        for k in list(validated.keys()):
            if str(k).lower() == "omega":
                omega_sig = validated.pop(k)
            elif str(k).lower() == "loki":
                loki_sig = validated.pop(k)
        family_status = self._cross_family_check(validated)
        schumann_corr = self._schumann_correlation(validated)
        active_families = sum(1 for a in family_status.values() if a)
        alert_signals = [s for s in validated.values() if s.signal_type == SignalType.ALERT]
        watch_signals = [s for s in validated.values() if s.signal_type == SignalType.WATCH]
        omega_active = omega_sig and omega_sig.signal_type in (SignalType.ALERT, SignalType.WATCH)
        loki_validation = self._loki_validation({"loki": loki_sig} if loki_sig else {})
        loki_confirms = loki_validation["loki_confirms"]
        veto_active = False
        veto_reason = ""
        note = ""
        if active_families >= 2 and len(alert_signals) >= 2 and schumann_corr > 0.3 and omega_active and loki_confirms:
            avg_conf = sum(s.confidence for s in alert_signals) / len(alert_signals)
            final, reached, conf = SignalType.ALERT, True, min(avg_conf + schumann_corr * 0.15 + loki_validation["loki_probability"] * 0.15, 0.98)
            note = "THREE ACTS ALIGNED: SNT + Omega + Loki"
        elif active_families >= 2 and len(alert_signals) >= 2 and schumann_corr > 0.3 and omega_active and not loki_confirms:
            avg_conf = sum(s.confidence for s in alert_signals) / len(alert_signals)
            final, reached, conf = SignalType.ALERT, True, min(avg_conf + schumann_corr * 0.2, 0.9)
            note = "SNT + Omega aligned; Loki pending"
            veto_active = True
            veto_reason = "Loki probability below threshold for full confirmation"
        elif active_families >= 2 and len(alert_signals) >= 2 and schumann_corr > 0.3 and not omega_active and loki_confirms:
            avg_conf = sum(s.confidence for s in alert_signals) / len(alert_signals)
            final, reached, conf = SignalType.ALERT, True, min(avg_conf + schumann_corr * 0.15 + loki_validation["loki_probability"] * 0.15, 0.9)
            note = "SNT + Loki aligned; Omega pending"
        elif active_families >= 2 and len(alert_signals) >= 2 and schumann_corr > 0.3 and not omega_active and not loki_validation["loki_active"]:
            # Legacy SNT-only ALERT (no Omega/Loki in signals — e.g. unit tests)
            avg_conf = sum(s.confidence for s in alert_signals) / len(alert_signals)
            final, reached, conf = SignalType.ALERT, True, min(avg_conf + schumann_corr * 0.2, 0.92)
            note = "SNT consensus (legacy, no Omega/Loki)"
        elif active_families >= 2 and (len(alert_signals) >= 1 or len(watch_signals) >= 2):
            avg_conf = sum(s.confidence for s in (alert_signals + watch_signals)) / max(len(alert_signals + watch_signals), 1)
            final, reached, conf = SignalType.WATCH, True, avg_conf * 0.8
            note = "Cross-family watch (SNT only)"
        elif len(alert_signals) >= 1:
            final, reached, conf = SignalType.WATCH, False, 0.35
            note = "Single-family alert, needs cross-validation"
        elif self.veto_check(list(validated.values())):
            final, reached, conf = SignalType.NO_SIGNAL, False, 0.0
            note = "Insufficient cross-family agreement"
            veto_active, veto_reason = True, note
        else:
            final, reached, conf = SignalType.NEUTRAL, False, 0.2
            note = "neutral"
        dual = self._dual_ask(omega_sig, final, alert_signals, watch_signals)
        if dual.get("omega_eleva_revision") and final in (SignalType.NEUTRAL, SignalType.NO_SIGNAL):
            final = SignalType.WATCH
            conf = max(conf, float(omega_sig.confidence) * 0.7 if omega_sig else conf)
            reached = False
            note = "Omega referencia eleva revision"
            dual["note_elevacion"] = note
            veto_active = False
        all_sigs = list(validated.values())
        if omega_sig:
            all_sigs.append(omega_sig)
        if loki_sig:
            all_sigs.append(loki_sig)
        return ConsensusResult(consensus_reached=reached, final_signal=final, confidence=conf, agent_signals=all_sigs, veto_active=veto_active, veto_reason=veto_reason, metadata={"families_active": active_families, "schumann_correlation": schumann_corr, "cross_family": family_status, "note": note, "loki": loki_validation, **dual})