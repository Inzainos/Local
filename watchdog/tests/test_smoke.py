"""Smoke tests: nada de red/sudo, solo que el pipeline basico no explote."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from watchdog import config as cfgmod  # noqa: E402
from watchdog.response import policy  # noqa: E402
from watchdog.storage import db  # noqa: E402


def test_load_config():
    cfg = cfgmod.load_config()
    assert cfg.get("scan", "light_interval_minutes") == 15
    assert cfg.get("scan", "heavy_interval_minutes") == 60


def test_policy_alert_only_without_intel():
    cfg = cfgmod.load_config()
    action = policy.decide(cfg, {"vt": None, "otx": None})
    assert action == policy.QUARANTINE


def test_policy_auto_delete_needs_both_vt_and_otx():
    cfg = cfgmod.load_config()
    intel_vt_only = {"vt": {"positives": 20, "total": 75}, "otx": {"hit": False}}
    assert policy.decide(cfg, intel_vt_only) == policy.QUARANTINE

    intel_both = {"vt": {"positives": 20, "total": 75}, "otx": {"hit": True}}
    assert policy.decide(cfg, intel_both) == policy.AUTO_DELETE


def test_db_roundtrip(tmp_path, monkeypatch):
    cfg = cfgmod.load_config()
    paths = {**cfg._raw["paths"], "db_path": str(tmp_path / "test.db")}
    monkeypatch.setattr(cfg, "_raw", {**cfg._raw, "paths": paths})
    with db.connect(cfg) as conn:
        db.record_incident(
            conn, scan_mode="light", finding_type="process",
            target="test", action="alert_only", notes="smoke test",
        )
        db.remember_ioc(conn, "deadbeef", "hash", "alert_only", {})
    with db.connect(cfg) as conn:
        row = db.recall_ioc(conn, "deadbeef")
        assert row["hit_count"] == 1
