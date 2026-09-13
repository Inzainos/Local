"""Unit tests for ConsensoVigilante — buffer vs immediate, dry_run, no network."""
from __future__ import annotations

import os
import sqlite3
import time

import pytest

from sentinel_omega.infrastructure.messaging.alert_service import (
    AlertService,
    AlertTemplates,
    Severity,
)
from sentinel_omega.infrastructure.messaging.consenso_vigilante import (
    ConsensoVigilante,
    reset_vigilante,
    webapp_reply_markup,
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    monkeypatch.setenv("SENTINEL_DRY_RUN", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBAPP_URL", raising=False)
    reset_vigilante()
    yield
    reset_vigilante()


@pytest.fixture
def vig():
    return ConsensoVigilante(dry_run=True, digest_minutes_override=60)


def _assert_no_network(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("Telegram API must not be called in these tests")

    monkeypatch.setattr(
        "sentinel_omega.infrastructure.api.telegram.send_alert", boom, raising=False
    )
    monkeypatch.setattr(
        "sentinel_omega.infrastructure.api.telegram.send_alert_gated", boom, raising=False
    )
    monkeypatch.setattr(
        "sentinel_omega.infrastructure.api.telegram.send_photo", boom, raising=False
    )


def test_routine_precursor_is_buffered_not_sent(vig, monkeypatch):
    _assert_no_network(monkeypatch)
    msg = AlertTemplates.precursor("schumann", "Schumann", 0.8, "latido alto")
    r = vig.ingest(msg)
    assert r["action"] == "buffered"
    assert r["unprecedented"] is False
    assert r["sent"] is False
    assert vig.pending_count() == 1
    assert vig.dispatched == []


def test_rojo_precursor_still_buffered(vig):
    """Severity does not page. Recurring precursor watches go to the hour."""
    msg = AlertTemplates.precursor("sismo_cluster", "Enjambre", 0.95, "cluster")
    assert msg.severity == Severity.ROJO
    r = vig.ingest(msg)
    assert r["action"] == "buffered"


def test_advertencia_and_consensus_buffered(vig):
    a = AlertTemplates.centinela_advertencia(0.65, -2.0, 450)
    c = AlertTemplates.consenso("geodynamic", "watch", 0.7, 4)
    assert vig.ingest(a)["action"] == "buffered"
    assert vig.ingest(c)["action"] == "buffered"
    assert vig.pending_count() == 2


def test_cimatica_nuevo_is_immediate(vig):
    msg = AlertTemplates.cimatica_nuevo(7, "bz:-8|wind:700", ambito="general")
    r = vig.ingest(msg, extra={"es_nuevo": True, "frecuencia": 1, "patron_id": 7})
    assert r["action"] == "immediate"
    assert r["unprecedented"] is True
    assert r["sent"] is True  # dry_run records as sent
    assert vig.pending_count() == 0
    assert vig.dispatched[-1].kind == "immediate"
    assert "SIN PRECEDENTES" in vig.dispatched[-1].html
    assert "pronóstico" in vig.dispatched[-1].html.lower() or "pronostico" in vig.dispatched[-1].html.lower() or "epicentro" in msg.html.lower()


def test_cimatica_consistente_is_buffered(vig):
    msg = AlertTemplates.cimatica_consistente(7, "bz:-8|wind:700", 3, "SISMO_M5")
    r = vig.ingest(msg, extra={"es_nuevo": False, "frecuencia": 3, "patron_id": 7})
    assert r["action"] == "buffered"
    assert r["unprecedented"] is False


def test_firma_nueva_immediate_recurrente_buffered(vig):
    nueva = AlertTemplates.firma_nueva("alfa1", "SISMO_M5", firma_id=1, recurrencia=1)
    r1 = vig.ingest(nueva, extra={"es_nueva": True, "estado": "nueva", "recurrencia": 1})
    assert r1["action"] == "immediate"

    # Recurring match: same firma, already seen.
    rec = AlertTemplates.consenso("geodynamic", "alert", 0.9, 6)
    r2 = vig.ingest(
        rec,
        extra={"firma_id": 1, "estado": "recurrente", "recurrencia": 4, "unprecedented": False},
    )
    assert r2["action"] == "buffered"


def test_system_dead_is_immediate(vig):
    msg = AlertTemplates.sistema_dead(45)
    r = vig.ingest(msg)
    assert r["action"] == "immediate"
    assert r["alert_type"] == "SYSTEM_DEAD"


def test_muro_novel_vs_seen(vig):
    novel = AlertTemplates.muro_breach("GEOFISICO", walls_active=2, novel=True)
    r1 = vig.ingest(novel, extra={"novel_muro": True, "muro_tipo": "GEOFISICO"})
    assert r1["action"] == "immediate"

    seen = AlertTemplates.muro_breach("GEOFISICO", walls_active=2, novel=False)
    r2 = vig.ingest(seen, extra={"novel_muro": False, "muro_tipo": "GEOFISICO"})
    assert r2["action"] == "buffered"


def test_hourly_digest_always_even_if_empty(vig):
    rec = vig.flush_digest(
        force=True,
        snapshot={
            "fantasma": 2.1,
            "nivel": "bajo",
            "muro_n": 0,
            "muro_breach": False,
            "loop_alive": True,
            "telemetry": {"bz_nT": -1.2, "viento_km_s": 410, "schumann_hz": 7.83, "kp": 2},
            "precursores": [],
        },
    )
    assert rec.sent is True
    assert rec.kind == "digest"
    assert "REPORTE HORARIO" in rec.html
    assert "Hora calma" in rec.html
    assert "pronóstico" in rec.html or "epicentro" in rec.html
    assert "Fantasma" in rec.html
    assert "vivo" in rec.html.lower()


def test_digest_includes_buffered_precursors(vig):
    vig.ingest(AlertTemplates.precursor("schumann", "Schumann", 0.6, "x"))
    vig.ingest(AlertTemplates.precursor("sismo_cluster", "Enjambre", 0.7, "y"))
    rec = vig.flush_digest(force=True, snapshot={"fantasma": 4.2, "nivel": "medio", "muro_n": 2, "loop_alive": True})
    assert vig.pending_count() == 0
    assert "Schumann" in rec.html
    assert "Enjambre" in rec.html
    assert "agruparon" in rec.html


def test_maybe_flush_respects_timer(vig):
    clock = {"t": 1_000.0}

    def now():
        return clock["t"]

    v = ConsensoVigilante(dry_run=True, digest_minutes_override=60, now_fn=now)
    first = v.maybe_flush(snapshot={"fantasma": 1.0, "loop_alive": True})
    assert first is not None and first.sent
    clock["t"] += 10 * 60
    second = v.maybe_flush(snapshot={"fantasma": 1.0, "loop_alive": True})
    assert second is None
    clock["t"] += 51 * 60
    third = v.maybe_flush(snapshot={"fantasma": 1.0, "loop_alive": True})
    assert third is not None and third.sent


def test_immediate_cooldown_does_not_spam(monkeypatch):
    clock = {"t": 5_000.0}
    v = ConsensoVigilante(dry_run=True, now_fn=lambda: clock["t"])
    msg = AlertTemplates.sistema_dead(12)
    r1 = v.ingest(msg)
    assert r1["sent"] is True
    r2 = v.ingest(msg)
    # dry_run _send still applies local cooldown
    assert r2["action"] == "immediate"
    assert r2["sent"] is False
    clock["t"] += 1801
    r3 = v.ingest(msg)
    assert r3["sent"] is True


def test_alert_service_telegram_goes_through_watcher(monkeypatch):
    _assert_no_network(monkeypatch)
    reset_vigilante()
    svc = AlertService(dry_run=True)
    msg = AlertTemplates.precursor("solar", "Solar", 0.55, "kp alto")
    out = svc.dispatch(msg, channels=["telegram", "log"])
    assert out["log"] is True
    assert out["telegram"] is True
    from sentinel_omega.infrastructure.messaging.consenso_vigilante import get_vigilante

    assert get_vigilante().pending_count() == 1
    assert get_vigilante().dispatched == []


def test_alert_service_correo_not_via_watcher():
    """correo/log stay as they are — dispatch still enqueues correo when conn given.
    We only assert the telegram path is buffered; correo without conn is skipped.
    """
    svc = AlertService(dry_run=True)
    msg = AlertTemplates.sistema_online()
    out = svc.dispatch(msg, channels=["telegram", "correo", "log"], conn=None)
    assert "correo" not in out
    assert out["log"] is True


def test_is_unprecedented_db_cimatica_and_firmas():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE tbl_cimatica_patrones ("
        "patron_id INTEGER PRIMARY KEY, clave TEXT, frecuencia INTEGER)"
    )
    conn.execute(
        "CREATE TABLE TBL_FIRMAS ("
        "firma_id INTEGER PRIMARY KEY, bot_name TEXT, event_class TEXT, "
        "estado TEXT, recurrencia INTEGER)"
    )
    conn.execute("INSERT INTO tbl_cimatica_patrones VALUES (1, 'aaa', 1)")
    conn.execute("INSERT INTO tbl_cimatica_patrones VALUES (2, 'bbb', 9)")
    conn.execute("INSERT INTO TBL_FIRMAS VALUES (10, 'alfa1', 'SISMO_M5', 'nueva', 1)")
    conn.execute("INSERT INTO TBL_FIRMAS VALUES (11, 'beta1', 'SISMO_M5', 'consolidada', 8)")
    v = ConsensoVigilante(dry_run=True)
    dummy = AlertTemplates.heartbeat("x")
    dummy.alert_type = "CIMATICA"
    assert v.is_unprecedented(dummy, extra={"patron_id": 1}, conn=conn) is True
    assert v.is_unprecedented(dummy, extra={"patron_id": 2}, conn=conn) is False
    dummy.alert_type = "FIRMA"
    assert v.is_unprecedented(dummy, extra={"firma_id": 10}, conn=conn) is True
    assert v.is_unprecedented(dummy, extra={"firma_id": 11}, conn=conn) is False
    conn.close()


def test_webapp_markup_requires_https(monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBAPP_URL", raising=False)
    assert webapp_reply_markup() is None
    monkeypatch.setenv("TELEGRAM_WEBAPP_URL", "http://127.0.0.1:8787/mini")
    assert webapp_reply_markup() is None
    monkeypatch.setenv("TELEGRAM_WEBAPP_URL", "https://panel.example.org/mini")
    mk = webapp_reply_markup()
    assert mk is not None
    btn = mk["inline_keyboard"][0][0]
    assert btn["web_app"]["url"] == "https://panel.example.org/mini"


def test_dry_run_never_imports_send_on_buffer(monkeypatch):
    _assert_no_network(monkeypatch)
    v = ConsensoVigilante(dry_run=True)
    for _ in range(5):
        v.ingest(AlertTemplates.precursor("schumann", "Schumann", 0.5, "z"))
    v.flush_digest(force=True, snapshot={"fantasma": 0.4, "loop_alive": True})
    # dry_run _send returns True without calling telegram
    assert v.dispatched[-1].dry_run is True
