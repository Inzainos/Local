"""El entrenamiento paralelo por bot debe dar el MISMO resultado que el
secuencial — si no, produce memoria sesgada y no sirve."""

from datetime import datetime, timedelta

import pytest

from sentinel_omega.infrastructure.database.schema import init_database
from sentinel_omega.infrastructure.pipeline.entrenamiento import (
    entrenar_reconocimiento,
)
from sentinel_omega.infrastructure.pipeline.entrenar_paralelo import (
    entrenar_reconocimiento_paralelo,
)


def _seed(db_path, n_eventos=8):
    """Mini-backcast: 14 días de clima espacial por evento + eventos M5+."""
    conn = init_database(db_path)
    base = datetime(2010, 6, 1)
    for ev in range(n_eventos):
        ts_ev = base + timedelta(days=20 * ev)
        for h in range(336):
            ts = (ts_ev - timedelta(hours=336 - h)).strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT OR IGNORE INTO tbl_clima_espacial_raw "
                "(timestamp_blk, bz_promedio, bz_min, bz_derivada, "
                " viento_solar_avg, viento_solar_max, kp_max, kp_promedio, "
                " proton_flux_10mev) VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, -3.0 - ev * 0.1, -11.0, 0.4, 430.0, 600.0, 5.5, 3.0, 12.0))
            conn.execute(
                "INSERT OR IGNORE INTO tbl_astronomia_cinematica "
                "(timestamp_blk, fase_lunar_pct, es_sicigia) VALUES (?,?,?)",
                (ts, 0.9, 1))
        blk = ts_ev.strftime("%Y-%m-%d %H:%M")
        conn.execute(
            "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
            "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
            "VALUES (?, 45, 1, 6.4)", (blk,))
    conn.commit()
    conn.close()


def _firmas_resumen(db_path):
    import sqlite3
    conn = sqlite3.connect(db_path)
    filas = conn.execute(
        "SELECT bot_name, event_class, id_nodo, recurrencia, estado "
        "FROM TBL_FIRMAS ORDER BY bot_name, event_class, id_nodo"
    ).fetchall()
    conn.close()
    return filas


def test_paralelo_igual_que_secuencial(tmp_path):
    seq = str(tmp_path / "seq.db")
    par = str(tmp_path / "par.db")
    _seed(seq)
    _seed(par)

    # Mismos bots en ambos (excluye alfa2 live-only, que no entrena del backcast)
    bots = ["alfa1", "beta1", "padre"]

    entrenar_reconocimiento(seq, bots=bots)
    entrenar_reconocimiento_paralelo(par, bots=bots, n_workers=3)

    resumen_seq = _firmas_resumen(seq)
    resumen_par = _firmas_resumen(par)

    assert resumen_seq == resumen_par, (
        "El paralelo NO coincide con el secuencial — memoria fragmentada"
    )
    assert len(resumen_seq) > 0


def test_paralelo_no_deja_bots_fuera(tmp_path):
    par = str(tmp_path / "par.db")
    _seed(par)
    res = entrenar_reconocimiento_paralelo(par, bots=["alfa1", "beta1"],
                                           n_workers=2)
    assert res["firmas_unidas"] > 0
    assert set(res["por_bot"].keys()) == {"alfa1", "beta1"}
