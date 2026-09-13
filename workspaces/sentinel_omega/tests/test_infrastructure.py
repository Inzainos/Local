"""Tests for infrastructure: Telegram bot, data pipeline, config, orchestrator."""

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from sentinel_omega.infrastructure.telegram.bot import SentinelTelegramBot, TelegramMessage
from sentinel_omega.core.shared.data_pipeline import (
    DatabaseManager,
    IngestionConfig,
    FILL_SENTINEL,
)
from sentinel_omega.config.sentinel_config import (
    SentinelOmegaConfig,
    LayerConfig,
    DatabaseConfig,
    SNTConfig,
)
from orchestrator import SentinelOrchestrator, SystemStatus
from sentinel_omega.core.shared.agent_base import ConsensusResult, SignalType


# ── TelegramBot ──────────────────────────────────────────────────────


class TestTelegramBot:

    def test_dry_run_no_token(self):
        bot = SentinelTelegramBot(token="", chat_id="")
        msg = TelegramMessage(
            layer="geodynamic", signal_type="ALERT", confidence=0.85,
            summary="Precursor correlation detected"
        )
        assert bot.send_alert(msg) is True

    def test_dry_run_with_details(self):
        bot = SentinelTelegramBot(token="", chat_id="")
        msg = TelegramMessage(
            layer="geodynamic", signal_type="ALERT", confidence=0.95,
            summary="Kp surge", details="Kp=7, Bz=-15nT"
        )
        assert bot.send_alert(msg) is True

    def test_layer_emojis_mapping(self):
        assert SentinelTelegramBot.LAYER_EMOJIS["geodynamic"] == "🌍"
        assert SentinelTelegramBot.LAYER_EMOJIS["system"] == "⚙️"

    def test_unknown_layer_gets_default_emoji(self):
        bot = SentinelTelegramBot(token="", chat_id="")
        msg = TelegramMessage(
            layer="unknown_layer", signal_type="TEST", confidence=0.5,
            summary="test"
        )
        assert bot.send_alert(msg) is True

    def test_send_heartbeat(self):
        bot = SentinelTelegramBot(token="", chat_id="")
        status = {"geodynamic": True}
        assert bot.send_heartbeat(status) is True

    @patch("sentinel_omega.infrastructure.api.telegram.get_session")
    def test_send_with_token(self, mock_get_session):
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_CHAT_ID"] = "12345"
        from sentinel_omega.infrastructure.api import telegram as tg
        tg._GATE.last_alert_time = 0
        tg._GATE.last_msg_type = ""

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_session = mock_get_session.return_value
        mock_session.post.return_value = mock_resp

        bot = SentinelTelegramBot(token="test_token", chat_id="12345")
        msg = TelegramMessage(
            layer="geodynamic", signal_type="ALERT", confidence=0.7,
            summary="Test alert"
        )
        assert bot.send_alert(msg) is True
        # Routine ALERT is buffered by ConsensoVigilante — no Telegram POST.
        mock_session.post.assert_not_called()

    @patch("sentinel_omega.infrastructure.api.telegram.get_session")
    def test_send_failure_returns_false(self, mock_get_session):
        import os
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_CHAT_ID"] = "12345"
        from sentinel_omega.infrastructure.api import telegram as tg
        tg._GATE.last_alert_time = 0
        tg._GATE.last_msg_type = ""

        mock_session = mock_get_session.return_value
        mock_session.post.side_effect = ConnectionError("Network error")

        bot = SentinelTelegramBot(token="test_token", chat_id="12345")
        msg = TelegramMessage(layer="geodynamic", signal_type="TEST", confidence=0.5, summary="fail")
        # Buffered ingest does not hit the network; returns True (queued for digest).
        assert bot.send_alert(msg) is True
        mock_session.post.assert_not_called()


# ── DatabaseManager ──────────────────────────────────────────────────


class TestDatabaseManager:

    def test_execute_and_query(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = DatabaseManager(db_path)
        mgr.execute("CREATE TABLE t (id INTEGER, val REAL)")
        mgr.execute("INSERT INTO t VALUES (1, 3.14)")
        mgr.execute("INSERT INTO t VALUES (2, 2.72)")
        df = mgr.query("SELECT * FROM t")
        assert len(df) == 2
        assert df["val"].iloc[0] == pytest.approx(3.14)

    def test_table_count(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        mgr = DatabaseManager(db_path)
        mgr.execute("CREATE TABLE t (id INTEGER)")
        mgr.execute("INSERT INTO t VALUES (1)")
        mgr.execute("INSERT INTO t VALUES (2)")
        mgr.execute("INSERT INTO t VALUES (3)")
        assert mgr.table_count("t") == 3


# ── IngestionConfig ──────────────────────────────────────────────────


class TestIngestionConfig:

    def test_defaults(self):
        config = IngestionConfig(source_name="test", db_path="test.db", table_name="t")
        assert config.resolution_hours == 6
        assert config.max_gap_hours == 3
        assert config.fill_value == FILL_SENTINEL
        assert config.year_start == 1994
        assert config.year_end == 2024


# ── SentinelOmegaConfig ─────────────────────────────────────────────


class TestConfig:

    def test_default_config(self):
        config = SentinelOmegaConfig()
        assert config.version == "2.5.0-shadow-node"
        assert "Elán" in config.author
        assert len(config.layers) == 2

    def test_lottery_disabled_by_default(self):
        config = SentinelOmegaConfig()
        assert config.layers["lottery"].enabled is False

    def test_active_layers(self):
        config = SentinelOmegaConfig()
        active = [k for k, v in config.layers.items() if v.enabled]
        assert "geodynamic" in active
        assert "lottery" not in active

    def test_refresh_intervals(self):
        config = SentinelOmegaConfig()
        assert config.layers["geodynamic"].refresh_interval_s == 300

    def test_snt_config_defaults(self):
        config = SentinelOmegaConfig()
        assert config.snt.friction_pearson_rho == -0.68
        assert config.snt.roche_threshold == 1.0
        assert config.snt.equilibrium_band == 0.1

    def test_coordinates(self):
        config = SentinelOmegaConfig()
        assert config.coordinates["lat"] == pytest.approx(19.31)
        assert config.coordinates["lon"] == pytest.approx(-98.24)

    def test_database_paths(self):
        config = SentinelOmegaConfig()
        assert "SENTINEL_OMEGA_PRO" in config.databases.geodynamic_db
        assert "TITAN_MEMORY" in config.databases.lottery_db


# ── SentinelOrchestrator ────────────────────────────────────────────


class FakeRunner:
    def __init__(self, result):
        self._result = result

    def run(self):
        if self._result is None:
            raise RuntimeError("no result")
        return self._result


class TestOrchestrator:

    def _config(self):
        return SentinelOmegaConfig()

    def test_init(self):
        orch = SentinelOrchestrator(self._config())
        assert orch._status.is_online is False
        assert orch._runner is None

    def test_run_cycle_no_runner(self):
        orch = SentinelOrchestrator(self._config())
        results = orch.run_cycle()
        assert results == {}

    def test_run_cycle_with_runner(self):
        consensus = ConsensusResult(
            consensus_reached=True,
            final_signal=SignalType.BULLISH,
            confidence=0.8,
            agent_signals=[],
        )
        orch = SentinelOrchestrator(self._config())
        orch._runner = FakeRunner(consensus)
        results = orch.run_cycle()
        assert "geodynamic" in results
        assert results["geodynamic"].final_signal == SignalType.BULLISH

    def test_run_cycle_handles_runner_error(self):
        orch = SentinelOrchestrator(self._config())
        orch._runner = FakeRunner(None)
        results = orch.run_cycle()
        assert "geodynamic" not in results

    def test_health_check(self):
        orch = SentinelOrchestrator(self._config())
        health = orch.health_check()
        assert health["geodynamic"] is False
        orch._status.is_online = True
        health = orch.health_check()
        assert health["geodynamic"] is True

    def test_status_uptime(self):
        orch = SentinelOrchestrator(self._config())
        time.sleep(0.05)
        status = orch.get_status()
        assert status.uptime_s >= 0.04
