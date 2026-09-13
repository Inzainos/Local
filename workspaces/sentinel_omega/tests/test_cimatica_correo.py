"""Tests de cimática (snapshot de patrones) y outbox de correo."""

import pytest

from sentinel_omega.infrastructure.database.schema import init_database
from sentinel_omega.core.firmas.cimatica import (
    FRECUENCIA_CONSISTENTE,
    banda,
    clave_patron,
    patrones_consistentes,
    registrar_snapshot,
)
from sentinel_omega.infrastructure.api.correo import (
    encolar_correo,
    enviar_pendientes,
)


@pytest.fixture
def db(tmp_path):
    conn = init_database(str(tmp_path / "test_cimatica.db"))
    yield conn
    conn.close()


FEATURES = {
    "bz_mean": -8.2, "kp_max": 6.0, "viento_avg": 540.0,
    "schumann_mean": 7.9, "fase_lunar": 0.95,
}


class TestBanda:

    def test_cero_para_pequenos(self):
        assert banda(0.0) == 0
        assert banda(0.3) == 0
        assert banda(-0.4) == 0

    def test_conserva_signo(self):
        assert banda(8.0) > 0
        assert banda(-8.0) < 0
        assert banda(8.0) == -banda(-8.0)

    def test_magnitudes_parecidas_misma_banda(self):
        assert banda(500.0) == banda(520.0)

    def test_magnitudes_distintas_banda_distinta(self):
        assert banda(3.0) != banda(300.0)

    def test_nan_es_cero(self):
        assert banda(float("nan")) == 0


class TestClavePatron:

    def test_determinista(self):
        assert clave_patron(FEATURES) == clave_patron(dict(FEATURES))

    def test_estado_parecido_misma_clave(self):
        cerca = dict(FEATURES, viento_avg=548.0)
        assert clave_patron(FEATURES) == clave_patron(cerca)

    def test_estado_distinto_clave_distinta(self):
        lejos = dict(FEATURES, bz_mean=12.0, kp_max=1.0)
        assert clave_patron(FEATURES) != clave_patron(lejos)

    def test_ignora_no_numericos(self):
        con_texto = dict(FEATURES, etiqueta="x")
        assert clave_patron(con_texto) == clave_patron(FEATURES)


class TestRegistrarSnapshot:

    def test_nuevo_guarda_telemetria_completa(self, db):
        pid, es_nuevo, frec = registrar_snapshot(db, FEATURES)
        assert es_nuevo is True
        assert frec == 1
        import json
        tele = json.loads(db.execute(
            "SELECT telemetria_json FROM tbl_cimatica_patrones "
            "WHERE patron_id = ?", (pid,)).fetchone()[0])
        assert tele["bz_mean"] == pytest.approx(-8.2)

    def test_existente_suma_uno(self, db):
        registrar_snapshot(db, FEATURES)
        pid, es_nuevo, frec = registrar_snapshot(db, FEATURES)
        assert es_nuevo is False
        assert frec == 2

    def test_nodo_y_general_separados(self, db):
        p1, n1, _ = registrar_snapshot(db, FEATURES)
        p2, n2, _ = registrar_snapshot(db, FEATURES, id_nodo=14)
        assert n1 and n2
        assert p1 != p2

    def test_etiqueta_event_class_despues(self, db):
        pid, _, _ = registrar_snapshot(db, FEATURES)
        registrar_snapshot(db, FEATURES, event_class="SISMO_M5")
        ec = db.execute(
            "SELECT event_class FROM tbl_cimatica_patrones "
            "WHERE patron_id = ?", (pid,)).fetchone()[0]
        assert ec == "SISMO_M5"

    def test_consistentes(self, db):
        for _ in range(FRECUENCIA_CONSISTENTE):
            registrar_snapshot(db, FEATURES, event_class="SISMO_M5")
        cons = patrones_consistentes(db)
        assert len(cons) == 1
        assert cons[0][4] == FRECUENCIA_CONSISTENTE

    def test_features_vacios_no_registran(self, db):
        pid, es_nuevo, frec = registrar_snapshot(db, {})
        assert pid == 0


class TestRetroetiquetadoYPoda:

    def test_evento_real_etiqueta_la_vispera(self, db):
        # El patrón se graba ANTES de saber qué desata; el evento lo etiqueta
        import time as _t
        registrar_snapshot(db, FEATURES)   # sin evento (ciclo vivo en calma)
        eventos = [{"epoch": _t.time() + 3600, "magnitude": 5.3}]
        from sentinel_omega.core.firmas.cimatica import retroetiquetar_patrones
        n = retroetiquetar_patrones(db, eventos)
        assert n == 1
        ec = db.execute(
            "SELECT event_class FROM tbl_cimatica_patrones").fetchone()[0]
        assert ec == "SISMO_M5"

    def test_evento_menor_no_etiqueta(self, db):
        import time as _t
        registrar_snapshot(db, FEATURES)
        from sentinel_omega.core.firmas.cimatica import retroetiquetar_patrones
        n = retroetiquetar_patrones(
            db, [{"epoch": _t.time() + 3600, "magnitude": 3.0}])
        assert n == 0

    def test_poda_elimina_ruido_conserva_lo_que_resalta(self, db):
        from sentinel_omega.core.firmas.cimatica import poda_cimatica
        # Ruido: viejo y sin evento asociado
        registrar_snapshot(db, FEATURES)
        db.execute(
            "UPDATE tbl_cimatica_patrones "
            "SET primera_vez = datetime('now', '-45 days')")
        # Lo que resalta: asociado a evento (igual de viejo)
        lejos = dict(FEATURES, bz_mean=12.0, kp_max=1.0)
        registrar_snapshot(db, lejos, event_class="SISMO_M5")
        db.execute(
            "UPDATE tbl_cimatica_patrones "
            "SET primera_vez = datetime('now', '-45 days') "
            "WHERE event_class IS NOT NULL")
        db.commit()

        podados = poda_cimatica(db)
        assert podados == 1
        restantes = db.execute(
            "SELECT event_class FROM tbl_cimatica_patrones").fetchall()
        assert restantes == [("SISMO_M5",)]

    def test_poda_respeta_la_gracia(self, db):
        from sentinel_omega.core.firmas.cimatica import poda_cimatica
        registrar_snapshot(db, FEATURES)   # recién nacido, sin evento
        assert poda_cimatica(db) == 0      # dentro de la gracia — se queda


class TestEntrenarCimatica:

    def test_graba_patrones_del_historico(self, db, tmp_path):
        # Sembrar un mini-backcast: bloques 1H + un evento significativo
        # (fixture de test — la regla cero-sintético aplica a producción)
        from datetime import datetime, timedelta
        db_path = str(tmp_path / "test_cimatica.db")

        base = datetime(2010, 6, 15)
        for h in range(336):
            ts = (base - timedelta(hours=336 - h)).strftime("%Y-%m-%d %H:%M")
            db.execute(
                "INSERT OR IGNORE INTO tbl_clima_espacial_raw "
                "(timestamp_blk, bz_promedio, bz_min, bz_derivada, "
                " viento_solar_avg, viento_solar_max, kp_max, kp_promedio, "
                " proton_flux_10mev) VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, -3.0, -11.0, 0.4, 430.0, 600.0, 5.5, 3.0, 12.0))
        ts_evento = base.strftime("%Y-%m-%d %H:%M")
        db.execute(
            "INSERT INTO tbl_historico_sismico_raw "
            "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
            "VALUES (?, 14, 3, 5.2)", (ts_evento,))
        db.commit()

        from sentinel_omega.core.firmas.cimatica import entrenar_cimatica
        stats = entrenar_cimatica(db_path)
        assert stats["eventos"] >= 1
        assert stats["patrones_nuevos"] >= 2   # general + nodo
        conn2 = __import__("sqlite3").connect(db_path)
        filas = conn2.execute(
            "SELECT ambito, event_class FROM tbl_cimatica_patrones").fetchall()
        assert ("general", "SISMO_M5") in filas
        assert ("nodo", "SISMO_M5") in filas


class TestCorreo:

    def test_encolar(self, db):
        cid = encolar_correo(db, "asunto x", "cuerpo y", tipo="REPORTE")
        fila = db.execute(
            "SELECT destinatario, tipo, estado FROM tbl_correo_salida "
            "WHERE correo_id = ?", (cid,)).fetchone()
        assert fila[0] == "elan.zainos.corona@gmail.com"
        assert fila[1] == "REPORTE"
        assert fila[2] == "PENDIENTE"

    def test_sin_credenciales_queda_pendiente(self, db, monkeypatch):
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASS", raising=False)
        encolar_correo(db, "alerta", "cuerpo")
        r = enviar_pendientes(db)
        assert r["enviados"] == 0
        assert r["pendientes"] == 1
        estado = db.execute(
            "SELECT estado FROM tbl_correo_salida").fetchone()[0]
        assert estado == "PENDIENTE"

    def test_outbox_vacio(self, db):
        r = enviar_pendientes(db)
        assert r == {"enviados": 0, "pendientes": 0, "fallidos": 0}
