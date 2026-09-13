"""Normalización 1NF de eventos_json → tbl_firma_eventos: la tabla hija es la
fuente de verdad, la migración rellena lo legado, y la vista reconstruye."""

import json

import pytest

from sentinel_omega.infrastructure.database.schema import (
    init_database,
    _migrate_firma_eventos,
)
from sentinel_omega.core.firmas.signature_engine import FirmaMemoria


@pytest.fixture
def conn(tmp_path):
    c = init_database(str(tmp_path / "norm.db"))
    yield c
    c.close()


def _features(**ov):
    f = {"bz_mean": -3.2, "bz_min": -12.0, "bz_deriv_std": 1.1,
         "viento_avg": 420.0, "viento_max": 610.0, "kp_mean": 3.1}
    f.update(ov)
    return f


class TestEventosEnTablaHija:

    def test_firma_nueva_escribe_evento_en_hija(self, conn):
        mem = FirmaMemoria(conn)
        fid, _, es_nueva = mem.registrar(
            "alfa1", "SISMO_M5", 45, _features(),
            "2010-06-01 00:00|nodo45|M5.2", "2010-06-01 00:00")
        assert es_nueva
        filas = conn.execute(
            "SELECT evento_ref FROM tbl_firma_eventos WHERE firma_id = ?",
            (fid,)).fetchall()
        assert filas == [("2010-06-01 00:00|nodo45|M5.2",)]
        # eventos_json ya NO se usa como almacén
        ev_json = conn.execute(
            "SELECT eventos_json FROM TBL_FIRMAS WHERE firma_id = ?",
            (fid,)).fetchone()[0]
        assert ev_json == "[]"

    def test_recurrencia_agrega_fila_no_reescribe_array(self, conn):
        mem = FirmaMemoria(conn)
        f = _features()
        fid, _, _ = mem.registrar("alfa1", "SISMO_M5", 45, f,
                                  "2010-06-01 00:00|nodo45|M5.2", "2010-06-01 00:00")
        for i in range(4):
            mem.registrar("alfa1", "SISMO_M5", 45, dict(f),
                          f"2010-06-0{i+2} 00:00|nodo45|M5.1",
                          f"2010-06-0{i+2} 00:00")
        n = conn.execute(
            "SELECT COUNT(*) FROM tbl_firma_eventos WHERE firma_id = ?",
            (fid,)).fetchone()[0]
        rec = conn.execute(
            "SELECT recurrencia FROM TBL_FIRMAS WHERE firma_id = ?",
            (fid,)).fetchone()[0]
        assert n == 5           # una fila por avistamiento
        assert rec == 5         # recurrencia coincide

    def test_orden_preservado(self, conn):
        mem = FirmaMemoria(conn)
        f = _features()
        fid, _, _ = mem.registrar("alfa1", "SISMO_M5", 45, f,
                                  "A|nodo45|M5.2", "2010-06-01 00:00")
        mem.registrar("alfa1", "SISMO_M5", 45, dict(f), "B|nodo45|M5.1",
                      "2010-06-02 00:00")
        orden = [r[0] for r in conn.execute(
            "SELECT evento_ref FROM tbl_firma_eventos WHERE firma_id = ? "
            "ORDER BY orden", (fid,))]
        assert orden == ["A|nodo45|M5.2", "B|nodo45|M5.1"]


class TestMigracion:

    def test_backfill_desde_eventos_json_legado(self, conn):
        # Simular una firma vieja con el array legado y sin filas hijas
        conn.execute(
            "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
            "features_json, recurrencia, estado, eventos_json) "
            "VALUES ('alfa1','SISMO_M5',45,'{}',3,'recurrente',?)",
            (json.dumps(["2001-01-01 00:00|nodo45|M5.0",
                         "2002-02-02 00:00|nodo45|M5.1",
                         "2003-03-03 00:00|nodo45|M5.2"]),))
        conn.commit()
        fid = conn.execute("SELECT firma_id FROM TBL_FIRMAS").fetchone()[0]

        _migrate_firma_eventos(conn)

        refs = [r[0] for r in conn.execute(
            "SELECT evento_ref FROM tbl_firma_eventos WHERE firma_id = ? "
            "ORDER BY orden", (fid,))]
        assert len(refs) == 3
        assert refs[0] == "2001-01-01 00:00|nodo45|M5.0"
        # eventos_json vaciado tras migrar (la hija es la fuente de verdad)
        assert conn.execute(
            "SELECT eventos_json FROM TBL_FIRMAS WHERE firma_id = ?",
            (fid,)).fetchone()[0] == "[]"

    def test_migracion_idempotente(self, conn):
        conn.execute(
            "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
            "features_json, recurrencia, estado, eventos_json) "
            "VALUES ('alfa1','SISMO_M5',45,'{}',1,'nueva',?)",
            (json.dumps(["X|nodo45|M5.0"]),))
        conn.commit()
        _migrate_firma_eventos(conn)
        _migrate_firma_eventos(conn)   # segunda vez: no duplica
        n = conn.execute("SELECT COUNT(*) FROM tbl_firma_eventos").fetchone()[0]
        assert n == 1


class TestMuestreo:

    def test_solo_guarda_la_muestra_pero_cuenta_todo(self, conn):
        from sentinel_omega.core.firmas.signature_engine import (
            CAP_EVENTOS_MUESTRA,
        )
        mem = FirmaMemoria(conn)
        f = _features()
        fid, _, _ = mem.registrar("alfa1", "SISMO_M5", 45, f,
                                  "2010-06-01 00:00|nodo45|M5.2", "2010-06-01 00:00")
        # muchas recurrencias del mismo patrón
        for i in range(50):
            mem.registrar("alfa1", "SISMO_M5", 45, dict(f),
                          f"2010-07-{i%28+1:02d} 00:00|nodo45|M5.1",
                          f"2010-07-{i%28+1:02d} 00:00")
        n_filas = conn.execute(
            "SELECT COUNT(*) FROM tbl_firma_eventos WHERE firma_id = ?",
            (fid,)).fetchone()[0]
        rec = conn.execute(
            "SELECT recurrencia FROM TBL_FIRMAS WHERE firma_id = ?",
            (fid,)).fetchone()[0]
        assert n_filas == CAP_EVENTOS_MUESTRA   # solo la muestra en disco
        assert rec == 51                        # pero el conteo es fiel

    def test_migracion_capa_la_muestra(self, conn):
        from sentinel_omega.core.firmas.signature_engine import (
            CAP_EVENTOS_MUESTRA,
        )
        refs = [f"2001-{i:02d}-01 00:00|nodo45|M5.0" for i in range(1, 25)]
        conn.execute(
            "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
            "features_json, recurrencia, estado, eventos_json) "
            "VALUES ('alfa1','SISMO_M5',45,'{}',24,'recurrente',?)",
            (json.dumps(refs),))
        conn.commit()
        _migrate_firma_eventos(conn)
        n = conn.execute("SELECT COUNT(*) FROM tbl_firma_eventos").fetchone()[0]
        assert n == CAP_EVENTOS_MUESTRA
        # el más viejo se conserva (orden=1)
        primero = conn.execute(
            "SELECT evento_ref FROM tbl_firma_eventos ORDER BY orden LIMIT 1"
        ).fetchone()[0]
        assert primero == "2001-01-01 00:00|nodo45|M5.0"


class TestVistaCompat:

    def test_vista_reconstruye_array(self, conn):
        mem = FirmaMemoria(conn)
        f = _features()
        fid, _, _ = mem.registrar("alfa1", "SISMO_M5", 45, f,
                                  "A|nodo45|M5.2", "2010-06-01 00:00")
        mem.registrar("alfa1", "SISMO_M5", 45, dict(f), "B|nodo45|M5.1",
                      "2010-06-02 00:00")
        row = conn.execute(
            "SELECT eventos_json, n_eventos, ts_primero "
            "FROM v_firma_eventos_json WHERE firma_id = ?", (fid,)).fetchone()
        assert set(json.loads(row[0])) == {"A|nodo45|M5.2", "B|nodo45|M5.1"}
        assert row[1] == 2
        assert row[2] == "2010-06-01 00:00"
