"""Tests for agent base, consensus, hierarchical validation, and agents."""

import time
import numpy as np
import pandas as pd
import pytest

from sentinel_omega.core.shared.agent_base import (
    AgentSignal,
    BaseAgent,
    ConfidenceLevel,
    ConsensusResult,
    PadreAgent,
    SignalType,
)
from sentinel_omega.layers.geodynamic.padre.agent import GeodynamicPadre


# ── Helpers ──────────────────────────────────────────────────────────


def _signal(name: str, signal_type: SignalType, confidence: float = 0.8) -> AgentSignal:
    return AgentSignal(
        agent_name=name,
        signal_type=signal_type,
        confidence=confidence,
        timestamp=time.time(),
    )


class ConcreteAgent(BaseAgent):
    def ingest(self, data):
        self._data = data

    def analyze(self):
        return self.emit_signal(SignalType.NEUTRAL, 0.5)

    def health_check(self):
        return True


# ── BaseAgent ────────────────────────────────────────────────────────


class TestBaseAgent:

    def test_emit_signal(self):
        agent = ConcreteAgent("test_agent", "test_layer")
        signal = agent.emit_signal(SignalType.ALERT, 0.9, reasoning="test")
        assert signal.agent_name == "test_agent"
        assert signal.signal_type == SignalType.ALERT
        assert signal.confidence == 0.9
        assert signal.reasoning == "test"
        assert signal.timestamp > 0

    def test_last_signal_stored(self):
        agent = ConcreteAgent("test", "layer")
        agent.emit_signal(SignalType.BULLISH, 0.7)
        assert agent._last_signal.signal_type == SignalType.BULLISH

    def test_analyze_returns_signal(self):
        agent = ConcreteAgent("test", "layer")
        signal = agent.analyze()
        assert isinstance(signal, AgentSignal)
        assert signal.signal_type == SignalType.NEUTRAL

    def test_signal_default_data(self):
        agent = ConcreteAgent("test", "layer")
        signal = agent.emit_signal(SignalType.NEUTRAL, 0.5)
        assert signal.data == {}


# ── PadreAgent (Asymmetric Loss) ─────────────────────────────────────


class TestPadreAsymmetricLoss:

    def test_missed_event_high_penalty(self):
        padre = GeodynamicPadre()
        loss = padre.asymmetric_loss(predicted=False, actual=True)
        assert loss == 10.0

    def test_false_alarm_low_penalty(self):
        padre = GeodynamicPadre()
        loss = padre.asymmetric_loss(predicted=True, actual=False)
        assert loss == 1.0

    def test_correct_prediction_zero_loss(self):
        padre = GeodynamicPadre()
        assert padre.asymmetric_loss(True, True) == 0.0
        assert padre.asymmetric_loss(False, False) == 0.0


# ── PadreAgent (Veto Check) ──────────────────────────────────────────


class TestVetoCheck:

    def test_veto_on_empty_signals(self):
        padre = GeodynamicPadre()
        assert padre.veto_check([]) is True

    def test_veto_on_all_neutral(self):
        padre = GeodynamicPadre()
        signals = [_signal("a", SignalType.NEUTRAL), _signal("b", SignalType.NEUTRAL)]
        assert padre.veto_check(signals) is True

    def test_no_veto_on_unanimous(self):
        padre = GeodynamicPadre()
        signals = [
            _signal("a", SignalType.ALERT),
            _signal("b", SignalType.ALERT),
            _signal("c", SignalType.ALERT),
        ]
        assert padre.veto_check(signals) is False

    def test_veto_on_split_signals(self):
        padre = GeodynamicPadre()
        signals = [
            _signal("a", SignalType.ALERT),
            _signal("b", SignalType.BULLISH),
            _signal("c", SignalType.BEARISH),
        ]
        assert padre.veto_check(signals) is True


# ── Hierarchical Validation (Junior → Senior) ────────────────────────


class TestHierarchicalValidation:

    def setup_method(self):
        self.padre = GeodynamicPadre()

    def test_junior_confirmed_by_senior(self):
        signals = [
            _signal("alfa1", SignalType.ALERT, 0.8),
            _signal("alfa2", SignalType.ALERT, 0.7),
            _signal("beta1", SignalType.NEUTRAL, 0.3),
            _signal("beta2", SignalType.NEUTRAL, 0.2),
            _signal("delta", SignalType.NEUTRAL, 0.3),
        ]
        validated = self.padre._validate_junior_with_senior(signals)
        assert validated["alfa2"].data.get("senior_confirmed") is True
        assert validated["alfa2"].confidence > 0.7

    def test_junior_unconfirmed_by_senior(self):
        signals = [
            _signal("alfa1", SignalType.NEUTRAL, 0.3),
            _signal("alfa2", SignalType.ALERT, 0.8),
            _signal("beta1", SignalType.NEUTRAL, 0.3),
            _signal("delta", SignalType.NEUTRAL, 0.3),
        ]
        validated = self.padre._validate_junior_with_senior(signals)
        assert validated["alfa2"].data.get("senior_confirmed") is False
        assert validated["alfa2"].confidence < 0.8
        assert validated["alfa2"].signal_type == SignalType.WATCH

    def test_training_years(self):
        assert GeodynamicPadre.AGENT_TRAINING_YEARS["alfa1"] == 30
        assert GeodynamicPadre.AGENT_TRAINING_YEARS["beta1"] == 30
        assert GeodynamicPadre.AGENT_TRAINING_YEARS["alfa2"] == 14
        assert GeodynamicPadre.AGENT_TRAINING_YEARS["beta2"] == 14
        assert GeodynamicPadre.AGENT_TRAINING_YEARS["delta"] == 10


# ── GeodynamicPadre Consensus ────────────────────────────────────────


class TestGeodynamicPadreConsensus:

    def setup_method(self):
        self.padre = GeodynamicPadre()

    def test_full_consensus_alert(self):
        signals = [
            _signal("alfa1", SignalType.ALERT, 0.8),
            _signal("beta1", SignalType.ALERT, 0.7),
            _signal("alfa2", SignalType.ALERT, 0.6),
            _signal("beta2", SignalType.ALERT, 0.6),
            _signal("delta", SignalType.ALERT, 0.5),
        ]
        result = self.padre.evaluate_consensus(signals)
        assert result.consensus_reached is True
        assert result.final_signal == SignalType.ALERT
        assert result.confidence > 0

    def test_no_signals_veto(self):
        result = self.padre.evaluate_consensus([])
        assert result.consensus_reached is False
        assert result.veto_active is True

    def test_single_family_no_consensus(self):
        signals = [
            _signal("alfa1", SignalType.ALERT, 0.9),
            _signal("alfa2", SignalType.ALERT, 0.8),
            _signal("beta1", SignalType.NEUTRAL, 0.3),
            _signal("beta2", SignalType.NEUTRAL, 0.2),
            _signal("delta", SignalType.NEUTRAL, 0.3),
        ]
        result = self.padre.evaluate_consensus(signals)
        assert result.final_signal != SignalType.ALERT or not result.consensus_reached

    def test_cross_family_alert(self):
        signals = [
            _signal("alfa1", SignalType.ALERT, 0.85),
            _signal("beta1", SignalType.ALERT, 0.8),
            _signal("alfa2", SignalType.NEUTRAL, 0.3),
            _signal("beta2", SignalType.NEUTRAL, 0.3),
            _signal("delta", SignalType.NEUTRAL, 0.3),
        ]
        result = self.padre.evaluate_consensus(signals)
        assert result.consensus_reached is True
        assert result.final_signal in (SignalType.ALERT, SignalType.WATCH)

    def test_schumann_correlation_boost(self):
        signals_with_schumann = [
            _signal("alfa1", SignalType.ALERT, 0.8),
            _signal("beta1", SignalType.ALERT, 0.9),
            _signal("delta", SignalType.ALERT, 0.6),
        ]
        result = self.padre.evaluate_consensus(signals_with_schumann)
        schumann_corr = self.padre._schumann_correlation(
            self.padre._validate_junior_with_senior(signals_with_schumann)
        )
        assert schumann_corr > 0

    def test_no_consensus_all_neutral(self):
        signals = [
            _signal("alfa1", SignalType.NEUTRAL, 0.3),
            _signal("beta1", SignalType.NEUTRAL, 0.3),
            _signal("delta", SignalType.NEUTRAL, 0.3),
        ]
        result = self.padre.evaluate_consensus(signals)
        assert result.consensus_reached is False


# ── Beta-2 Agent (Atmospheric Chemistry) ─────────────────────────────


class TestBeta2AgentAtmospheric:

    def test_analyze_with_pressure_anomaly(self):
        from sentinel_omega.layers.geodynamic.beta2.agent import Beta2Agent
        agent = Beta2Agent()
        agent.ingest({
            "pressure_gradient": {
                "mean_pressure": 1002.0,
                "pressure_spread": 15.0,
                "low_pressure_stations": ["tlaxcala", "guerrero"],
            },
            "air_quality": {"so2": 35.0, "co": 200.0, "pm2_5": 10.0},
        })
        signal = agent.analyze()
        assert signal.signal_type in (SignalType.ALERT, SignalType.WATCH)
        assert signal.data.get("pressure_stress", 0) > 0

    def test_analyze_normal_atmosphere(self):
        from sentinel_omega.layers.geodynamic.beta2.agent import Beta2Agent
        agent = Beta2Agent()
        agent.ingest({
            "pressure_gradient": {
                "mean_pressure": 1013.0,
                "pressure_spread": 3.0,
                "low_pressure_stations": [],
            },
            "air_quality": {"so2": 5.0, "co": 100.0, "pm2_5": 8.0},
        })
        signal = agent.analyze()
        assert signal.signal_type == SignalType.NEUTRAL

    def test_analyze_fog_detection(self):
        from sentinel_omega.layers.geodynamic.beta2.agent import Beta2Agent
        agent = Beta2Agent()
        agent.ingest({
            "pressure_gradient": {"mean_pressure": 1005.0, "pressure_spread": 8.0},
            "atmospheric_readings": [
                {"station": "tlaxcala", "visibility_m": 500},
            ],
        })
        signal = agent.analyze()
        assert signal.data.get("fog_detected") is True

    def test_analyze_no_data(self):
        from sentinel_omega.layers.geodynamic.beta2.agent import Beta2Agent
        agent = Beta2Agent()
        agent.ingest({})
        signal = agent.analyze()
        assert signal.signal_type == SignalType.NO_SIGNAL

    def test_health_check(self):
        from sentinel_omega.layers.geodynamic.beta2.agent import Beta2Agent
        agent = Beta2Agent()
        assert agent.health_check() is False
        agent.ingest({"pressure_gradient": {"mean_pressure": 1013.0}})
        assert agent.health_check() is True


# ── Delta Agent (Financial Cross-Correlation) ─────────────────────────


class TestDeltaAgentFinancial:

    def test_analyze_extreme_fear(self):
        from sentinel_omega.layers.geodynamic.delta.agent import DeltaAgent
        agent = DeltaAgent()
        agent.ingest({
            "fear_greed": 10.0,
            "vix": 45.0,
            "btc_dominance": 0.65,
            "yield_spread": -0.5,
        })
        signal = agent.analyze()
        assert signal.signal_type in (SignalType.ALERT, SignalType.WATCH)
        assert signal.data["market_fear_score"] > 0.5

    def test_analyze_normal_markets(self):
        from sentinel_omega.layers.geodynamic.delta.agent import DeltaAgent
        agent = DeltaAgent()
        agent.ingest({
            "fear_greed": 50.0,
            "vix": 18.0,
            "btc_dominance": 0.52,
            "yield_spread": 1.0,
        })
        signal = agent.analyze()
        assert signal.signal_type == SignalType.NEUTRAL

    def test_analyze_with_crypto_topology(self):
        from sentinel_omega.layers.geodynamic.delta.agent import DeltaAgent
        agent = DeltaAgent()
        agent.ingest({
            "fear_greed": 15.0,
            "vix": 38.0,
            "crypto_ratios": {"ETH": 0.05, "SOL": 0.002, "BNB": 0.01, "XRP": 0.001},
        })
        signal = agent.analyze()
        assert signal.signal_type in SignalType

    def test_health_check(self):
        from sentinel_omega.layers.geodynamic.delta.agent import DeltaAgent
        agent = DeltaAgent()
        assert agent.health_check() is False
        agent.ingest({"fear_greed": 30.0})
        assert agent.health_check() is True
