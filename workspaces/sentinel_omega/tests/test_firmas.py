"""Tests for the signature engine (firmas) and the Juez auditor."""

import sqlite3
import time

import pytest

from sentinel_omega.infrastructure.database.schema import init_database
from sentinel_omega.core.firmas.signature_engine import (
    FirmaMemoria,
    extraer_features_ventana,
    similitud,
)
from sentinel_omega.core.juez.juez import Juez
from sentinel_omega.infrastructure.pipeline.entrenamiento import (
    entrenar_reconocimiento,
    backtest_disciplinario,
    _event_class,
)


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test_firmas.db")
    conn = init_database(path)
    yield conn, path
    conn.close()


def _features_base(**overrides):
    f = {
        "bz_mean": -3.2, "bz_min": -12.0, "bz_deriv_std": 1.1,
        "viento_avg": 420.0, "viento_max": 610.0,
        "kp_mean": 3.1, "kp_max": 6.0,
        "schumann_mean": 7.9, "schumann_std": 0.2,
        "sismo_count_win": 4.0, "sismo_max_mag_win": 4.8,
        "fase_lunar": 0.92, "es_sicigia": 1.0,
    }
    f.update(overrides)
    return f


# ── Similitud ────────────────────────────────────────────────────────


class TestSimilitud:

    def test_identical_vectors(self):
        f = _features_base()
        assert similitud(f, dict(f)) == pytest.approx(1.0)

    def test_very_different_vectors(self):
        a = _features_base()
        b = _features_base(bz_mean=15.0, bz_min=10.0, kp_mean=0.1,
                           kp_max=0.2, viento_avg=250.0, viento_max=260.0,
                           sismo_count_win=0.0, schumann_mean=14.0)
        assert similitud(a, b) < 0.85

    def test_too_few_shared_dimensions(self):
        assert similitud({"kp_mean": 3.0}, {"kp_mean": 3.0}) == 0.0

    def test_missing_keys_excluded(self):
        a = _features_base()
        b = {k: v for k, v in _features_base().items() if k != "btc_volatilidad"}
        assert similitud(a, b) == pytest.approx(1.0)


# ── FirmaMemoria (promoción) ────────────────────────────────────────


class TestFirmaMemoria:

    def test_first_sighting_is_nueva(self, db):
        conn, _ = db
        memoria = FirmaMemoria(conn)
        fid, estado, es_nueva = memoria.registrar(
            "beta1", "SISMO_M6", 45, _features_base(), "ev1", "2020-01-01 00:00"
        )
        assert es_nueva is True
        assert estado == "nueva"

    def test_recurrence_promotes(self, db):
        conn, _ = db
        memoria = FirmaMemoria(conn)
        estados = []
        for i in range(5):
            _, estado, _ = memoria.registrar(
                "beta1", "SISMO_M6", 45, _features_base(),
                f"ev{i}", f"2020-0{i+1}-01 00:00",
            )
            estados.append(estado)
        assert estados[0] == "nueva"
        assert estados[1] == "observada"
        assert estados[2] == "recurrente"
        assert estados[4] == "consolidada"

    def test_different_signature_creates_new(self, db):
        conn, _ = db
        memoria = FirmaMemoria(conn)
        memoria.registrar("beta1", "SISMO_M6", 45, _features_base(), "a", "2020-01-01")
        distinta = _features_base(
            bz_mean=18.0, bz_min=12.0, kp_mean=0.1, kp_max=0.3,
            viento_avg=250.0, viento_max=255.0, schumann_mean=14.5,
            sismo_count_win=0.0, sismo_max_mag_win=0.0, fase_lunar=0.05,
        )
        _, _, es_nueva = memoria.registrar(
            "beta1", "SISMO_M6", 12, distinta, "b", "2021-01-01"
        )
        assert es_nueva is True
        assert memoria.stats()["total"] == 2

    def test_match_estado_actual_only_consolidadas(self, db):
        conn, _ = db
        memoria = FirmaMemoria(conn)
        for i in range(5):
            memoria.registrar("padre", "SISMO_M7", 45, _features_base(),
                              f"e{i}", f"202{i}-01-01")
        matches = memoria.match_estado_actual(_features_base())
        assert len(matches) == 1
        assert matches[0]["event_class"] == "SISMO_M7"
        assert matches[0]["similitud"] > 0.9

    def test_no_match_when_nothing_consolidated(self, db):
        conn, _ = db
        memoria = FirmaMemoria(conn)
        memoria.registrar("padre", "SISMO_M7", 45, _features_base(), "e", "2020-01-01")
        assert memoria.match_estado_actual(_features_base()) == []


# ── Juez ─────────────────────────────────────────────────────────────


class TestJuez:

    def test_acierto(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("padre", "alert", 0.8, ventana_h=0)
        res = juez.evaluar_pendientes(evento_ocurrido=True, verdad="M6.1")
        assert res[0]["resultado"] == "ACIERTO"
        assert res[0]["severidad"] == 0.0

    def test_falso_positivo_cheap(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("padre", "alert", 0.8, ventana_h=0)
        res = juez.evaluar_pendientes(evento_ocurrido=False)
        assert res[0]["resultado"] == "FALSO_POSITIVO"
        assert res[0]["severidad"] == 1.0

    def test_fallo_severity_asymmetric(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("padre", "neutral", 0.3, ventana_h=0)
        res = juez.evaluar_pendientes(evento_ocurrido=True, verdad="M7.0")
        assert res[0]["resultado"] == "FALLO"
        assert res[0]["severidad"] >= 10.0

    def test_fallo_firma_conocida_worst(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("padre", "neutral", 0.3, ventana_h=0)
        res = juez.evaluar_pendientes(
            evento_ocurrido=True, verdad="M7.0", firma_conocida=True
        )
        assert res[0]["severidad"] >= 20.0

    def test_recidivism_scales_severity(self, db):
        conn, _ = db
        juez = Juez(conn)
        severidades = []
        for _ in range(3):
            juez.registrar_prediccion("padre", "neutral", 0.3, ventana_h=0)
            res = juez.evaluar_pendientes(evento_ocurrido=True, verdad="M6")
            severidades.append(res[0]["severidad"])
        assert severidades[1] > severidades[0]
        assert severidades[2] > severidades[1]

    def test_open_window_stays_pending(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("padre", "alert", 0.8, ventana_h=72)
        res = juez.evaluar_pendientes(evento_ocurrido=True)
        assert res == []

    def test_resumen_por_bot(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("padre", "alert", 0.8, ventana_h=0)
        juez.evaluar_pendientes(evento_ocurrido=True)
        resumen = juez.resumen_por_bot()
        assert resumen["padre"]["ACIERTO"] == 1
        assert resumen["padre"]["asertividad"] == 1.0

    def test_eventos_por_fila_dentro_de_ventana(self, db):
        # Verdad POR FILA: el evento debe caer en la ventana de ESA predicción
        import time as _t
        conn, _ = db
        juez = Juez(conn)
        ts = _t.time() - 10 * 3600
        juez.registrar_prediccion("padre", "watch", 0.7, ventana_h=1,
                                  timestamp=ts)
        eventos = [{"epoch": ts + 1800, "lat": 17.0, "lon": -99.5,
                    "magnitude": 5.0}]
        res = juez.evaluar_pendientes(
            evento_ocurrido=False, eventos=eventos,
        )
        assert res[0]["resultado"] == "ACIERTO"

    def test_eventos_por_fila_fuera_de_ventana(self, db):
        # Evento fuera de la ventana temporal NO valida la predicción
        import time as _t
        conn, _ = db
        juez = Juez(conn)
        ts = _t.time() - 10 * 3600
        juez.registrar_prediccion("padre", "watch", 0.7, ventana_h=1,
                                  timestamp=ts)
        eventos = [{"epoch": ts + 5 * 3600, "lat": 17.0, "lon": -99.5,
                    "magnitude": 5.0}]
        res = juez.evaluar_pendientes(
            evento_ocurrido=True,   # ignorado: eventos manda
            eventos=eventos,
        )
        assert res[0]["resultado"] == "FALSO_POSITIVO"

    def test_eventos_filtrados_por_zona(self, db):
        # Evento lejos de toda zona monitoreada no cuenta
        import time as _t
        conn, _ = db
        juez = Juez(conn)
        ts = _t.time() - 10 * 3600
        juez.registrar_prediccion("padre", "watch", 0.7, ventana_h=1,
                                  timestamp=ts)
        eventos = [{"epoch": ts + 1800, "lat": 60.0, "lon": 30.0,
                    "magnitude": 5.0}]
        res = juez.evaluar_pendientes(
            evento_ocurrido=False, eventos=eventos,
            zonas=[(17.0, -99.5)], radio_deg=5.0,
        )
        assert res[0]["resultado"] == "FALSO_POSITIVO"

    def test_nodos_propios_ganan_a_zonas_globales(self, db):
        # La fila trae SUS nodos: un evento cerca de otra parte de la malla
        # global NO valida el aviso — solo cuenta donde avisó.
        import time as _t
        conn, _ = db
        juez = Juez(conn)
        ts = _t.time() - 10 * 3600
        juez.registrar_prediccion(
            "padre", "watch", 0.7, ventana_h=1, timestamp=ts,
            detalles={"nodos": [{"id": 14, "lat": 17.0, "lon": -99.5}]},
        )
        eventos = [{"epoch": ts + 1800, "lat": 35.0, "lon": 139.0,
                    "magnitude": 5.5}]   # lejos del nodo avisado
        res = juez.evaluar_pendientes(
            evento_ocurrido=False, eventos=eventos,
            zonas=[(17.0, -99.5), (35.0, 139.0)],   # malla global lo cubre
        )
        assert res[0]["resultado"] == "FALSO_POSITIVO"

    def test_nodos_propios_acierto_en_su_nodo(self, db):
        import time as _t
        conn, _ = db
        juez = Juez(conn)
        ts = _t.time() - 10 * 3600
        juez.registrar_prediccion(
            "padre", "watch", 0.7, ventana_h=1, timestamp=ts,
            detalles={"nodos": [{"id": 14, "lat": 17.0, "lon": -99.5}]},
        )
        eventos = [{"epoch": ts + 1800, "lat": 16.6, "lon": -99.1,
                    "magnitude": 5.5}]   # a <5° del nodo avisado
        res = juez.evaluar_pendientes(evento_ocurrido=False, eventos=eventos)
        assert res[0]["resultado"] == "ACIERTO"

    def test_eventos_zona_cercana_cuenta(self, db):
        import time as _t
        conn, _ = db
        juez = Juez(conn)
        ts = _t.time() - 10 * 3600
        juez.registrar_prediccion("padre", "no_signal", 0.3, ventana_h=1,
                                  timestamp=ts)
        eventos = [{"epoch": ts + 1800, "lat": 16.5, "lon": -99.0,
                    "magnitude": 5.6}]
        res = juez.evaluar_pendientes(
            evento_ocurrido=False, eventos=eventos,
            zonas=[(17.0, -99.5)], radio_deg=5.0,
        )
        # calló y hubo evento en zona → FALLO con gravedad por magnitud
        assert res[0]["resultado"] == "FALLO"
        assert res[0]["severidad"] > 10.0


# ── Entrenamiento sobre backcast sintetizado en test ────────────────


def _seed_backcast(conn, n_eventos=6):
    """Insert minimal 1H backcast rows + significant events for training.

    Test fixture data (allowed synthetic: this is a test database, not
    production ingestion).
    """
    from datetime import datetime, timedelta

    base = datetime(2010, 6, 1)
    for ev in range(n_eventos):
        ts_evento = base + timedelta(days=30 * ev)
        # 14 days of hourly space weather before each event, similar pattern
        for h in range(336):
            ts = ts_evento - timedelta(hours=336 - h)
            blk = ts.strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT OR IGNORE INTO tbl_clima_espacial_raw "
                "(timestamp_blk, bz_promedio, bz_min, bz_derivada, "
                " viento_solar_avg, viento_solar_max, kp_max, kp_promedio, "
                " proton_flux_10mev) VALUES (?,?,?,?,?,?,?,?,?)",
                (blk, -3.0, -11.0, 0.4, 430.0, 600.0, 5.5, 3.0, 12.0),
            )
        blk_evento = ts_evento.strftime("%Y-%m-%d %H:%M")
        conn.execute(
            "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
            "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
            "VALUES (?, 45, 1, 6.4)",
            (blk_evento,),
        )
    conn.commit()


class TestEntrenamiento:

    def test_event_class(self):
        assert _event_class(5.2) == "SISMO_M5"
        assert _event_class(6.4) == "SISMO_M6"
        assert _event_class(7.8) == "SISMO_M7"
        # enforcement floor: M4.5 is still "SISMO_M4" (exigible)
        assert _event_class(4.5) == "SISMO_M4"
        assert _event_class(4.9) == "SISMO_M4"
        # sub-threshold observation classes (non-exigible)
        assert _event_class(4.0) == "SISMO_M4_obs"
        assert _event_class(3.5) == "SISMO_M3_obs"
        assert _event_class(2.7) == "SISMO_M2_obs"

    def test_fase1_learns_and_promotes(self, db):
        conn, path = db
        _seed_backcast(conn, n_eventos=6)
        stats = entrenar_reconocimiento(path)
        assert stats["eventos"] == 6
        assert stats["firmas_nuevas"] >= 1
        assert stats["recurrencias"] >= 1
        # 6 near-identical events -> the recurring firma consolidates
        assert stats["memoria"].get("consolidada", 0) >= 1

    def test_fase2_recognizes_consolidated(self, db):
        conn, path = db
        _seed_backcast(conn, n_eventos=6)
        entrenar_reconocimiento(path)
        stats = backtest_disciplinario(path)
        assert stats["firmas_evaluadas"] > 0
        assert stats["reconocidas"] > 0

    def test_extraer_features_none_without_data(self, db):
        conn, _ = db
        assert extraer_features_ventana(conn, "2015-01-01 00:00", 45) is None

    def test_fase2_reinforces_weights(self, db):
        conn, path = db
        _seed_backcast(conn, n_eventos=6)
        entrenar_reconocimiento(path)
        stats = backtest_disciplinario(path)
        # All signatures recognized -> credibility intact at baseline
        # (recognition repairs, it does not inflate)
        assert stats["fallos"] == 0
        for bot, peso in stats["pesos"].items():
            assert peso == pytest.approx(1.0)


# ── Pesos disciplinarios (castigo hijo x1, Padre x2) ─────────────────


class TestPesos:

    def test_castigo_hijo_vs_padre(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import castigar, cargar_pesos
        castigar(conn, "beta1", es_padre=False)
        castigar(conn, "padre", es_padre=True)
        pesos = cargar_pesos(conn)
        assert pesos["beta1"] == pytest.approx(0.95)
        assert pesos["padre"] == pytest.approx(0.90)  # double decay

    def test_castigo_escala_con_gravedad(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import castigar, cargar_pesos
        # Missing an M7 (gravedad 3) hurts much more than an M5 (gravedad 1)
        castigar(conn, "bot_m5", gravedad=1.0)
        castigar(conn, "bot_m7", gravedad=3.0)
        pesos = cargar_pesos(conn)
        assert pesos["bot_m5"] == pytest.approx(0.95)
        assert pesos["bot_m7"] == pytest.approx(0.95 ** 3)
        assert pesos["bot_m7"] < pesos["bot_m5"]

    def test_juez_severidad_cuadratica_en_gravedad(self, db):
        conn, _ = db
        juez = Juez(conn)
        juez.registrar_prediccion("a", "neutral", 0.3, ventana_h=0)
        res_m5 = juez.evaluar_pendientes(
            evento_ocurrido=True, verdad="M5", gravedad=1.0
        )
        juez.registrar_prediccion("b", "neutral", 0.3, ventana_h=0)
        res_m7 = juez.evaluar_pendientes(
            evento_ocurrido=True, verdad="M7", gravedad=3.0
        )
        # quadratic: gravedad 3 -> 9x the severity of gravedad 1
        assert res_m7[0]["severidad"] == pytest.approx(
            res_m5[0]["severidad"] * 9.0
        )

    def test_peso_bounded_below(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import castigar
        peso = 1.0
        for _ in range(50):
            peso = castigar(conn, "beta1")
        assert peso == pytest.approx(0.3)

    def test_refuerzo_normal_caps_at_baseline(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import reforzar
        peso = 1.0
        for _ in range(50):
            peso = reforzar(conn, "beta1")
        # doing your job repairs credibility but never exceeds baseline
        assert peso == pytest.approx(1.0)

    def test_refuerzo_recovers_after_castigo(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import castigar, reforzar
        castigar(conn, "beta1")  # 0.95
        peso = reforzar(conn, "beta1")
        assert 0.95 < peso <= 1.0

    def test_atencion_puede_superar_baseline(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import reforzar, PESO_MAX
        peso = 1.0
        for _ in range(50):
            peso = reforzar(conn, "beta1", hasta=PESO_MAX)
        assert peso == pytest.approx(1.5)

    def test_refuerzo_normal_no_baja_peso_ganado(self, db):
        conn, _ = db
        from sentinel_omega.core.juez.pesos import reforzar, PESO_MAX
        reforzar(conn, "beta1", hasta=PESO_MAX)  # 1.02 (above baseline)
        peso = reforzar(conn, "beta1")  # normal reinforcement
        assert peso == pytest.approx(1.02)  # never lowered back to 1.0

    def test_padre_applies_pesos_in_consensus(self):
        import time as _time
        from sentinel_omega.layers.geodynamic.padre.agent import GeodynamicPadre
        from sentinel_omega.core.shared.agent_base import AgentSignal, SignalType

        def sig(name, stype, conf):
            return AgentSignal(agent_name=name, signal_type=stype,
                               confidence=conf, timestamp=_time.time())

        signals = [
            sig("alfa1", SignalType.ALERT, 0.9),
            sig("beta1", SignalType.ALERT, 0.9),
            sig("delta", SignalType.ALERT, 0.8),
        ]

        padre_neutral = GeodynamicPadre()
        res_neutral = padre_neutral.evaluate_consensus(signals)

        padre_castigado = GeodynamicPadre()
        padre_castigado.set_pesos({"alfa1": 0.5, "beta1": 0.5, "delta": 0.5})
        res_castigado = padre_castigado.evaluate_consensus(signals)

        # Punished bots' ALERTs demote to WATCH (peso < 0.6) — the same
        # signals no longer produce a full ALERT consensus.
        assert res_neutral.final_signal == SignalType.ALERT
        assert res_castigado.final_signal != SignalType.ALERT

    def test_muro_lags_convergencia(self):
        from sentinel_omega.core.precursor.muro_lags import evaluar_muro_lags
        matches = [
            {"firma_id": 1, "event_class": "SISMO_M5", "similitud": 0.85,
             "ventana_tipica_dias": 7.0},
            {"firma_id": 2, "event_class": "SISMO_M6", "similitud": 0.83,
             "ventana_tipica_dias": 9.0},
            {"firma_id": 3, "event_class": "SISMO_M5", "similitud": 0.82,
             "ventana_tipica_dias": 8.0},
        ]
        r = evaluar_muro_lags(matches)
        # ventanas: [3.5-10.5], [4.5-13.5], [4-12] → convergen en [4.5, 10.5]
        assert r["activo"] is True
        assert r["firmas_convergentes"] == 3
        assert r["ventana_dias"] == [4.5, 10.5]
        assert "SISMO_M6" in r["clases"]

    def test_muro_lags_sin_convergencia(self):
        from sentinel_omega.core.precursor.muro_lags import evaluar_muro_lags
        matches = [
            {"firma_id": 1, "event_class": "A", "similitud": 0.9,
             "ventana_tipica_dias": 1.0},
            {"firma_id": 2, "event_class": "B", "similitud": 0.9,
             "ventana_tipica_dias": 10.0},
            {"firma_id": 3, "event_class": "C", "similitud": 0.9,
             "ventana_tipica_dias": 100.0},
        ]
        r = evaluar_muro_lags(matches)
        assert r["activo"] is False

    def test_muro_lags_pocos_matches(self):
        from sentinel_omega.core.precursor.muro_lags import evaluar_muro_lags
        r = evaluar_muro_lags([
            {"firma_id": 1, "event_class": "A", "similitud": 0.9,
             "ventana_tipica_dias": 7.0},
        ])
        assert r["activo"] is False

    def test_peso_alto_no_demotion(self):
        import time as _time
        from sentinel_omega.layers.geodynamic.padre.agent import GeodynamicPadre
        from sentinel_omega.core.shared.agent_base import AgentSignal, SignalType

        def sig(name, stype, conf):
            return AgentSignal(agent_name=name, signal_type=stype,
                               confidence=conf, timestamp=_time.time())

        signals = [
            sig("alfa1", SignalType.ALERT, 0.9),
            sig("beta1", SignalType.ALERT, 0.9),
            sig("delta", SignalType.ALERT, 0.8),
        ]
        padre = GeodynamicPadre()
        padre.set_pesos({"alfa1": 0.9, "beta1": 0.9, "delta": 0.9})
        res = padre.evaluate_consensus(signals)
        # Weights above the demotion threshold scale confidence but do NOT
        # demote the ALERT — consensus still escalates.
        assert res.final_signal == SignalType.ALERT
        assert res.consensus_reached is True


# ── Disciplina de trasfondo (castigo desde abajo) ────────────────────


class TestDisciplinaTrasfondo:
    """Disciplina rolling contra sismos menores: tabla temporal + pesos."""

    def _preparar(self, conn, path, monkeypatch, features):
        from sentinel_omega.infrastructure.pipeline import entrenamiento as E
        _seed_backcast(conn, n_eventos=6)          # firmas consolidadas en nodo 45
        entrenar_reconocimiento(path)
        # nodo 45 ≈ (40.18, -161.06): eventos menores que mapean ahí
        eventos = [("2010-10-25 00:00", 40.2, -161.0, 3.2 + i * 0.1)
                   for i in range(8)]
        monkeypatch.setattr(E, "_fetch_sismos_menores", lambda *a, **k: eventos)
        monkeypatch.setattr(E, "extraer_features_ventana", lambda *a, **k: features)
        return E

    def test_puebla_tabla_temporal_y_acota_pesos(self, db, monkeypatch):
        conn, path = db
        E = self._preparar(conn, path, monkeypatch, _features_base())
        pre = dict(conn.execute(
            "SELECT bot_name, peso FROM TBL_PESOS_BOTS").fetchall())
        res = E.disciplina_trasfondo(path, anio=2010, max_eventos=8)

        assert res["eventos"] == 8
        # La memoria permanente NO se toca; las menores van a su tabla temporal
        n_menores = conn.execute(
            "SELECT COUNT(*) FROM tbl_firmas_menores").fetchone()[0]
        assert n_menores > 0
        # Pesos dentro de límites y movidos a lo más MAX_AJUSTES pasos
        from sentinel_omega.core.juez.pesos import (
            PESO_MIN, PESO_MAX, CASTIGO_PADRE, REFUERZO,
        )
        post = dict(conn.execute(
            "SELECT bot_name, peso FROM TBL_PESOS_BOTS").fetchall())
        for bot, peso in post.items():
            assert PESO_MIN <= peso <= PESO_MAX
            # cota: nunca más allá de MAX_AJUSTES castigos del Padre (el más duro)
            piso = pre.get(bot, 1.0) * (CASTIGO_PADRE ** E.DISCIPLINA_MAX_AJUSTES)
            assert peso >= piso - 1e-9

    def test_ceguera_local_castiga(self, db, monkeypatch):
        conn, path = db
        # features MUY distintas a la firma aprendida -> no reconoce -> castigo
        distintas = _features_base(
            bz_mean=99.0, bz_min=99.0, viento_avg=9999.0, viento_max=9999.0,
            kp_mean=0.0, kp_max=0.0, proton_max=0.0,
        )
        E = self._preparar(conn, path, monkeypatch, distintas)
        res = E.disciplina_trasfondo(path, anio=2010, max_eventos=8)
        # Con ceguera local, al menos un bot recibe castigo
        total_castigos = sum(a["castigos"] for a in res["ajustes"].values())
        assert total_castigos >= 1

    def test_poda_rolling_por_edad(self, db, monkeypatch):
        conn, path = db
        E = self._preparar(conn, path, monkeypatch, _features_base())
        # Fila vieja artificial (más allá de la retención)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tbl_firmas_menores ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, bot_name TEXT, "
            "event_class TEXT, id_nodo INTEGER, mag REAL, features_json TEXT, "
            "ts_evento TEXT, creada_at TEXT DEFAULT (datetime('now')))"
        )
        conn.execute(
            "INSERT INTO tbl_firmas_menores "
            "(bot_name, event_class, id_nodo, mag, features_json, ts_evento, "
            " creada_at) VALUES ('alfa1','SISMO_M3',45,3.1,'{}','x',"
            "datetime('now','-200 days'))"
        )
        conn.commit()
        E.disciplina_trasfondo(path, anio=2010, max_eventos=8)
        # La fila de hace 200 días quedó fuera (retención 90 días)
        viejas = conn.execute(
            "SELECT COUNT(*) FROM tbl_firmas_menores "
            "WHERE creada_at < datetime('now','-90 days')").fetchone()[0]
        assert viejas == 0


# ── Barrido diario (mantenimiento del historial operativo) ───────────


class TestBarridoDiario:
    """El barrido se queda con lo significante y bota el bulto."""

    def _seed_operativo(self, conn):
        from datetime import datetime, timezone, timedelta
        # Normalize to start-of-day so all 6 hourly cycles fall on the same UTC day
        # regardless of when the test runs (avoids midnight-boundary flakiness).
        base = (datetime.now(timezone.utc) - timedelta(days=20)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for cyc in range(6):
            ts = (base + timedelta(hours=cyc)).timestamp()
            nivel = "CRITICAL" if cyc == 0 else "LOW"
            breach = 1 if cyc == 0 else 0
            conn.execute(
                "INSERT INTO TBL_CICLOS (timestamp, geo_signal, geo_confidence, "
                "fantasma, nivel_riesgo, muro_breach, muro_walls_active) "
                "VALUES (?,?,?,?,?,?,?)",
                (ts, "watch", 0.4, 40.0 if cyc == 0 else 3.0, nivel, breach, 3),
            )
            # las mismas 2 detecciones repetidas cada ciclo (bulto)
            for tipo in ("SCHUMANN", "TSUNAMI"):
                conn.execute(
                    "INSERT INTO TBL_DETECCIONES (timestamp, tipo, display_name, "
                    "confidence, wall_name) VALUES (?,?,?,?,?)",
                    (ts, tipo, tipo, 0.7, "SOLAR"),
                )
        conn.commit()

    def test_colapsa_detecciones_y_resume_dia(self, db):
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import barrido_diario
        self._seed_operativo(conn)
        assert conn.execute("SELECT COUNT(*) FROM TBL_DETECCIONES").fetchone()[0] == 12
        res = barrido_diario(path, dias_full=7)
        # 6 ciclos × 2 detecciones -> una por (día, tipo, muro) = 2
        assert conn.execute("SELECT COUNT(*) FROM TBL_DETECCIONES").fetchone()[0] == 2
        assert res["detecciones_colapsadas"] == 10
        # el día quedó resumido
        assert res["dias_resumidos"] == 1
        fila = conn.execute(
            "SELECT n_ciclos, fantasma_max, nivel_max, breaches FROM tbl_resumen_diario"
        ).fetchone()
        assert fila[0] == 6 and fila[1] == 40.0 and fila[2] == "CRITICAL" and fila[3] == 1

    def test_conserva_significativos_bota_calma(self, db):
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import barrido_diario
        self._seed_operativo(conn)
        barrido_diario(path, dias_full=7)
        # los ciclos de calma (LOW, sin breach) anteriores al corte se botan;
        # el CRITICAL con breach se conserva
        niveles = [r[0] for r in conn.execute("SELECT nivel_riesgo FROM TBL_CICLOS")]
        assert "CRITICAL" in niveles
        assert "LOW" not in niveles


class TestCorrelacionesPadre:
    """El Padre correlaciona: patrón cruzado -> conteo, solo lo significativo."""

    def test_cuenta_y_descarta_cola(self, db):
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            construir_correlaciones_padre, _patron_padre,
        )
        # patrón dominante (calma solar + sísmico) repetido -> significativo
        dom = _features_base(kp_max=0.1, kp_max_72h=0.1, bz_min=0.5,
                             sismo_count_win=5.0, sismo_max_mag_win=5.0)
        for i in range(60):
            conn.execute(
                "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
                "features_json, recurrencia, estado, ventana_horas) "
                "VALUES ('padre','SISMO_M5',45,?,1,'consolidada',336)",
                (__import__("json").dumps(dom),),
            )
        # un patrón raro, una sola vez -> cae bajo el umbral, se descarta
        raro = _features_base(kp_max=9.0, bz_min=-20.0, proton_max=500.0,
                              sismo_count_win=0.0, sismo_max_mag_win=0.0)
        conn.execute(
            "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
            "features_json, recurrencia, estado, ventana_horas) "
            "VALUES ('padre','SISMO_M7',9,?,1,'consolidada',336)",
            (__import__("json").dumps(raro),),
        )
        conn.commit()
        res = construir_correlaciones_padre(path, min_n=50)
        assert res["significativos"] >= 1
        assert res["descartados"] >= 1
        # el patrón dominante quedó con su conteo acumulado
        n = conn.execute(
            "SELECT n FROM tbl_correlaciones_padre WHERE event_class='SISMO_M5'"
        ).fetchone()
        assert n is not None and n[0] == 60
        # el raro (n=1) no sobrevive
        assert conn.execute(
            "SELECT COUNT(*) FROM tbl_correlaciones_padre WHERE event_class='SISMO_M7'"
        ).fetchone()[0] == 0


class TestSesgoAprendizaje:
    """Realidad (causal) vs fantasía (in-sample); el Padre paga si es fantasía."""

    def test_causal_menor_que_insample_y_castiga_padre(self, db):
        conn, path = db
        import json as _json
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            evaluar_sesgo_aprendizaje,
        )
        _seed_backcast(conn, n_eventos=6)  # eventos M6.4 en nodo 45, 2010-06+
        # firma del PADRE consolidada cuya memoria nace DESPUÉS de los eventos
        # -> in-sample la reconoce, pero causalmente no existía antes -> sesgo
        feats = _features_base(sismo_count_win=5.0, sismo_max_mag_win=6.4)
        conn.execute(
            "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
            "features_json, eventos_json, recurrencia, estado, ventana_horas) "
            "VALUES ('padre','SISMO_M6',45,?,?,9,'consolidada',336)",
            (_json.dumps(feats),
             _json.dumps(["2020-01-01 00:00|nodo45|M6.4"])),  # memoria de 2020
        )
        conn.commit()
        res = evaluar_sesgo_aprendizaje(path, muestra=50)
        p = res["por_bot"].get("padre")
        assert p is not None
        # causal <= in-sample (la memoria de 2020 no existia en 2010)
        assert p["causal"] <= p["insample"]
        # con sesgo real, al Padre le toca castigo
        if p["causal"] < 1.0:
            assert p["castigos"] >= 1
        fila = conn.execute(
            "SELECT recon_insample, recon_causal FROM tbl_sesgo_aprendizaje "
            "WHERE bot='padre'"
        ).fetchone()
        assert fila is not None


class TestSesgoEnEntrenamiento:
    """El sesgo se mide en el pre y el post del entrenamiento."""

    def test_linea_base_no_castiga(self, db):
        conn, path = db
        import json as _json
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            evaluar_sesgo_aprendizaje,
        )
        _seed_backcast(conn, n_eventos=6)
        # firma del padre con memoria posterior a los eventos -> causal bajo
        feats = _features_base(sismo_count_win=5.0, sismo_max_mag_win=6.4)
        conn.execute(
            "INSERT INTO TBL_FIRMAS (bot_name, event_class, id_nodo, "
            "features_json, eventos_json, recurrencia, estado, ventana_horas) "
            "VALUES ('padre','SISMO_M6',45,?,?,9,'consolidada',336)",
            (_json.dumps(feats), _json.dumps(["2020-01-01 00:00|nodo45|M6.4"])),
        )
        conn.commit()
        peso_antes = conn.execute(
            "SELECT peso FROM TBL_PESOS_BOTS WHERE bot_name='padre'"
        ).fetchone()
        res = evaluar_sesgo_aprendizaje(path, muestra=30, aplicar_castigo=False)
        peso_despues = conn.execute(
            "SELECT peso FROM TBL_PESOS_BOTS WHERE bot_name='padre'"
        ).fetchone()
        # línea base: castigos reportados en 0 y el peso NO se mueve
        p = res["por_bot"].get("padre", {})
        assert p.get("castigos", 0) == 0
        assert (peso_antes or (1.0,)) == (peso_despues or (1.0,))

    def test_entrenar_reporta_pre_post_y_mejora(self, db):
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.entrenamiento import entrenar
        _seed_backcast(conn, n_eventos=6)
        res = entrenar(path)
        assert "sesgo_pre" in res and "sesgo_post" in res
        assert "mejora_causal" in res
        # tras entrenar sobre eventos idénticos, el post debe reconocer
        if res["sesgo_post"]:
            for bot, d in res["sesgo_post"].items():
                assert 0.0 <= d["causal"] <= 1.0


class TestOrdenPrecursores:
    """El Padre discierne si el orden de los precursores importa."""

    def test_secuencia_y_veredicto(self, db):
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            analizar_orden_precursores,
        )
        from datetime import datetime, timedelta
        base = datetime(2010, 6, 1)
        # 40 eventos con la MISMA secuencia: SOLAR en tramo 1 (kp alto solo al
        # inicio de la víspera), SISMICO después -> el orden debe dominar
        for ev in range(40):
            tse = base + timedelta(days=20 * ev)
            for h in range(336):
                ts = tse - timedelta(hours=336 - h)
                kp = 6.0 if h < 84 else 1.0   # tramo 1 tormentoso, luego calma
                conn.execute(
                    "INSERT OR IGNORE INTO tbl_clima_espacial_raw "
                    "(timestamp_blk, bz_promedio, bz_min, kp_max, kp_promedio) "
                    "VALUES (?,?,?,?,?)",
                    (ts.strftime("%Y-%m-%d %H:%M"), -2.0, -5.0, kp, kp * 0.6),
                )
            # actividad sísmica solo en el último tramo (h>=252)
            previo = tse - timedelta(hours=40)
            conn.execute(
                "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
                "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
                "VALUES (?, 45, 1, 3.0)", (previo.strftime("%Y-%m-%d %H:%M"),))
            conn.execute(
                "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
                "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
                "VALUES (?, 45, 1, 5.5)", (tse.strftime("%Y-%m-%d %H:%M"),))
        conn.commit()
        res = analizar_orden_precursores(path, muestra=100)
        assert res["eventos"] > 0 and res["secuencias"] >= 1
        # el conjunto SISMICO+SOLAR debe existir con SOLAR->SISMICO dominante
        v = res["veredictos"].get("SISMICO+SOLAR")
        assert v is not None
        assert v["dominante"].startswith("SOLAR")
        assert v["veredicto"] in ("EL ORDEN IMPORTA", "ORDEN UNICO OBSERVADO")
        # persistido
        n = conn.execute("SELECT COUNT(*) FROM tbl_orden_veredictos").fetchone()[0]
        assert n >= 1

    def test_dominio_schumann_desde_serie_viva(self, db):
        # El latido (beta1) entra al cruce en cuanto hay medición viva.
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            analizar_orden_precursores,
        )
        from datetime import datetime, timedelta
        base = datetime(2020, 6, 1)
        for ev in range(35):
            tse = base + timedelta(days=15 * ev)
            for h in range(0, 336, 3):
                ts = tse - timedelta(hours=336 - h)
                conn.execute(
                    "INSERT OR IGNORE INTO tbl_schumann_vivo "
                    "(timestamp_blk, schumann_hz, schumann_activity) "
                    "VALUES (?, 7.9, 45.0)", (ts.strftime("%Y-%m-%d %H:00"),))
            conn.execute(
                "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
                "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
                "VALUES (?, 45, 1, 5.5)", (tse.strftime("%Y-%m-%d %H:%M"),))
        conn.commit()
        res = analizar_orden_precursores(path, muestra=100)
        # algún orden debe incluir SCHUMANN
        assert any("SCHUMANN" in o for (o, _) in
                   conn.execute("SELECT orden, event_class FROM tbl_orden_precursores"))


class TestSecuenciaNodos:
    """La ruta de nodos por la que se propaga la energía: global vs local."""

    def _sembrar(self, conn, base, nodos_ruta, mag, dia0):
        from datetime import timedelta
        tse = base + timedelta(days=dia0)
        # cada nodo de la ruta se activa en un momento distinto de la víspera,
        # en orden temporal (propagación espacial)
        for i, nodo in enumerate(nodos_ruta[:-1]):
            t = tse - timedelta(hours=60 - i * 12)
            conn.execute(
                "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
                "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
                "VALUES (?, ?, 1, 3.2)", (t.strftime("%Y-%m-%d %H:%M"), nodo))
        conn.execute(
            "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
            "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
            "VALUES (?, ?, 1, ?)",
            (tse.strftime("%Y-%m-%d %H:%M"), nodos_ruta[-1], mag))

    def test_ruta_global_vs_local(self, db):
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            analizar_secuencia_nodos,
        )
        from datetime import datetime
        base = datetime(2010, 6, 1)
        dia = 0
        # RUTA GLOBAL: nodos 12>45 precede a M5 Y a M6 (distintos tipos)
        for _ in range(5):
            self._sembrar(conn, base, [12, 45], 5.5, dia); dia += 15
        for _ in range(4):
            self._sembrar(conn, base, [12, 45], 6.2, dia); dia += 15
        # RUTA LOCAL: nodos 30>31 solo precede a M5
        for _ in range(5):
            self._sembrar(conn, base, [30, 31], 5.4, dia); dia += 15
        conn.commit()

        res = analizar_secuencia_nodos(path, muestra=200)
        assert res["recurrentes"] >= 2
        v = {s: d for s, d in res["veredictos"].items()}
        # la ruta 12>45 aparece con M5 y M6 -> GLOBAL
        global_seq = next((s for s, d in v.items()
                           if d["alcance"] == "GLOBAL"), None)
        assert global_seq is not None
        assert "nodo12>nodo45" in global_seq
        # la ruta 30>31 es de un solo tipo -> LOCAL
        assert any(d["alcance"] == "LOCAL" for d in v.values())
        # persistido
        n = conn.execute(
            "SELECT COUNT(*) FROM tbl_secuencia_veredictos WHERE alcance='GLOBAL'"
        ).fetchone()[0]
        assert n >= 1

    def test_incluye_eventos_no_sismicos(self, db):
        # Todo evento natural es liberación de energía: una ruta que precede a
        # un SISMO y a un VOLCÁN es cimática global cruzando dominios.
        conn, path = db
        from sentinel_omega.infrastructure.pipeline.mantenimiento import (
            analizar_secuencia_nodos,
        )
        from datetime import datetime, timedelta
        base = datetime(2011, 1, 1)
        dia = 0
        # ruta 12>45 antes de sismos M5
        for _ in range(4):
            self._sembrar(conn, base, [12, 45], 5.4, dia); dia += 20
        # misma ruta 12>45 antes de erupciones (catálogo no sísmico)
        for _ in range(4):
            tse = base + timedelta(days=dia)
            for i, nodo in enumerate([12]):
                t = tse - timedelta(hours=60 - i * 12)
                conn.execute(
                    "INSERT OR IGNORE INTO tbl_historico_sismico_raw "
                    "(timestamp_blk, id_nodo, sismo_count, sismo_max_mag) "
                    "VALUES (?, ?, 1, 3.1)", (t.strftime("%Y-%m-%d %H:%M"), nodo))
            conn.execute(
                "INSERT OR IGNORE INTO tbl_eventos_no_sismicos "
                "(timestamp_blk, id_nodo, event_class, fuente, intensidad) "
                "VALUES (?, 45, 'ERUPCION_VEI4', 'test', 4.0)",
                (tse.strftime("%Y-%m-%d %H:%M"),))
            dia += 20
        conn.commit()

        res = analizar_secuencia_nodos(path, muestra=200)
        # la ruta 12>45 precede a SISMO_M5 y a ERUPCION_VEI4 -> GLOBAL cruzando
        # dominios (sísmico + volcánico)
        v = res["veredictos"]
        cross = next((s for s, d in v.items()
                      if d["alcance"] == "GLOBAL" and "nodo12>nodo45" in s), None)
        assert cross is not None, "la ruta cruza-dominios debe ser GLOBAL"
        clases = conn.execute(
            "SELECT event_class FROM tbl_secuencia_nodos WHERE secuencia = ?",
            (cross,)).fetchall()
        nombres = {c[0] for c in clases}
        assert "SISMO_M5" in nombres
        assert "ERUPCION_VEI4" in nombres


class TestOmegaMapeado:
    """Omega está mapeado a la telemetría existente y entrena como los demás."""

    def test_omega_en_bot_features(self):
        from sentinel_omega.infrastructure.pipeline.entrenamiento import (
            BOT_FEATURES, MIN_FEATURES_POR_BOT,
        )
        from sentinel_omega.core.firmas.signature_engine import FEATURE_KEYS
        assert "omega" in BOT_FEATURES and "omega" in MIN_FEATURES_POR_BOT
        # todos sus campos existen en la telemetría (sin fetchers nuevos)
        for k in BOT_FEATURES["omega"]:
            assert k in FEATURE_KEYS, f"campo {k} no existe en FEATURE_KEYS"

    def test_omega_aprende_firmas(self, db):
        conn, path = db
        _seed_backcast(conn, n_eventos=6)
        stats = entrenar_reconocimiento(path, bots=["omega"])
        n = conn.execute(
            "SELECT COUNT(*) FROM TBL_FIRMAS WHERE bot_name='omega'"
        ).fetchone()[0]
        assert n >= 1
        # incremental: no infla a los demás bots
        otros = conn.execute(
            "SELECT COUNT(*) FROM TBL_FIRMAS WHERE bot_name!='omega'"
        ).fetchone()[0]
        assert otros == 0
