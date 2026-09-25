"""Pruebas del adaptador que conecta MotorTurnos con Ollama.

Sin red: se sustituye `generate` del agente. Lo que se comprueba aquí no es
que Ollama responda, sino que el adaptador no deshaga ninguna de las
decisiones que costaron medirse hoy.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.turnos import MotorTurnos  # noqa: E402
from engine.turnos_ollama import AdaptadorTurnos  # noqa: E402


class _LifecycleFalso:
    def __init__(self):
        self.cargas = []

    def ensure_exclusive(self, model, settle_seconds=1.0, num_ctx=None):
        self.cargas.append((model, num_ctx))


# ─── la ventana, que es lo que costo medir ───────────────────────────────────

def test_cargar_le_pasa_la_ventana_a_ensure_exclusive():
    """Sin num_ctx en la CARGA, Ollama aparta la ventana completa.

    Medido el 2026-09-24: deepseek-r1:8b sin acotar queda en 23,93 GiB sobre un
    host de 11,71, y el generate posterior no puede reducirla sin recargar.
    """
    lc = _LifecycleFalso()
    AdaptadorTurnos(lifecycle=lc).cargar("deepseek-r1:8b", 12288)
    assert lc.cargas == [("deepseek-r1:8b", 12288)]


def test_sin_lifecycle_no_revienta():
    AdaptadorTurnos(lifecycle=None).cargar("llama3.2:3b", 4096)  # no debe lanzar


def test_el_agente_lleva_la_ventana_como_num_ctx():
    ag = AdaptadorTurnos()._agente("mistral:7b", 16384)
    assert ag.num_ctx == 16384


def test_un_agente_por_modelo_y_ventana():
    """El mismo modelo con dos ventanas es, en memoria, dos cosas distintas."""
    a = AdaptadorTurnos()
    assert a._agente("llama3.2:3b", 16384) is a._agente("llama3.2:3b", 16384)
    assert a._agente("llama3.2:3b", 16384) is not a._agente("llama3.2:3b", 8192)


# ─── dos decisiones que un descuido desharia ──────────────────────────────────

def test_el_turno_no_tiene_modelo_de_respaldo():
    """Si el turno de mistral cae a llama, el nivel ya no es el que dice ser.

    Y su techo de RAM tampoco. El motor ya trata un turno caido como REFINO con
    confianza 0 y sigue; conmutar de modelo en silencio seria peor.
    """
    assert AdaptadorTurnos()._agente("mistral:7b", 16384).fallback_model is None


def test_el_agente_no_gobierna_su_propia_carga():
    """La carga la hace `cargar`, una vez por turno.

    Si el agente tambien llamara a ensure_exclusive, descargaria y recargaria el
    mismo modelo en medio de su propio turno.
    """
    assert AdaptadorTurnos(lifecycle=_LifecycleFalso())._agente(
        "llama3.2:3b", 16384).lifecycle is None


# ─── parseo e integracion con el motor ───────────────────────────────────────

def test_invocar_devuelve_los_cuatro_campos(monkeypatch):
    a = AdaptadorTurnos()
    ag = a._agente("llama3.2:3b", 16384)
    monkeypatch.setattr(ag, "generate", lambda **k: (
        "VEREDICTO: REFINO\nCONFIANZA: 71\nBORRADOR:\ndef f(): pass\n"
        "OBJECIONES:\n- no valida nada\n"))
    v, c, b, o = a.invocar("llama3.2:3b", "contexto", 16384)
    assert (v, c, o) == ("REFINO", 71, ["no valida nada"])
    assert "def f()" in b


def test_una_respuesta_ilegible_no_aprueba_el_turno(monkeypatch):
    a = AdaptadorTurnos()
    ag = a._agente("llama3.2:3b", 16384)
    monkeypatch.setattr(ag, "generate", lambda **k: "pues no sé, algo así")
    v, c, _, _ = a.invocar("llama3.2:3b", "contexto", 16384)
    assert (v, c) == ("REFINO", 0)


def test_el_motor_y_el_adaptador_encajan(monkeypatch, tmp_path):
    """El motor llama a `cargar` e `invocar` con lo que el adaptador espera."""
    lc = _LifecycleFalso()
    a = AdaptadorTurnos(lifecycle=lc)
    for modelo, ventana in (("llama3.2:3b", 16384), ("qwen2.5-coder:7b", 32768)):
        monkeypatch.setattr(
            a._agente(modelo, ventana), "generate",
            lambda **k: "VEREDICTO: PASO\nCONFIANZA: 90\nBORRADOR:\nlisto\nOBJECIONES:\nninguna")

    perfil = {
        "consenso": {"umbral_nivel": 85},
        "memoria": {"store": str(tmp_path / "t.jsonl"), "turnos_visibles": 3},
        "escalado_contexto": {"por_ventana": {16384: 4000, 32768: 8000},
                              "por_turno": {1: 1.0, 2: 0.6},
                              "reserva_para_generacion": 0.25},
        "codigo": {"ligero": {"techo_ram_gb": 6.4, "turnos": [
            {"model": "llama3.2:3b", "rol": "esbozo", "ctx": 16384},
            {"model": "qwen2.5-coder:7b", "rol": "programador", "ctx": 32768},
        ]}},
    }
    r = MotorTurnos(perfil, invocar=a.invocar, cargar_exclusivo=a.cargar
                    ).correr_nivel("t1", "escribe f(x)", "codigo", "ligero")

    assert lc.cargas == [("llama3.2:3b", 16384), ("qwen2.5-coder:7b", 32768)]
    assert r.media == 90.0 and r.alcanzo_umbral
    assert r.borrador_final == "listo"


# ─── el Capitan ──────────────────────────────────────────────────────────────
# La version anterior (moe_captain.classify_task) devolvia `task_types[0]`
# cuando el modelo salia del esquema, con un aviso en el log. Quien llamaba no
# tenia forma de distinguir una clasificacion de un valor de relleno.

def _fingir_capitan(monkeypatch, respuesta=None, excepcion=None):
    import engine.turnos_ollama as mod

    def falso(**k):
        if excepcion:
            raise excepcion
        return respuesta
    monkeypatch.setattr(mod, "run_with_tools", falso)


def test_el_capitan_clasifica(monkeypatch):
    from engine.turnos_ollama import elegir_area_y_nivel
    _fingir_capitan(monkeypatch, '{"area": "codigo", "nivel": "intermedio"}')
    d = elegir_area_y_nivel("escribe una funcion")
    assert (d.area, d.nivel, d.seguro) == ("codigo", "intermedio", True)


def test_si_el_capitan_no_responde_la_decision_no_es_fiable(monkeypatch):
    """EL PUNTO: los valores de arranque van MARCADOS, no disfrazados."""
    from engine.turnos_ollama import elegir_area_y_nivel
    _fingir_capitan(monkeypatch, excepcion=TimeoutError("se agoto"))
    d = elegir_area_y_nivel("da igual")
    assert d.seguro is False, ("un fallo del capitan no puede devolverse como "
                              "una clasificacion: el area equivocada es una "
                              "tuberia equivocada y eso no se arregla escalando")


def test_fuera_del_esquema_tampoco_es_fiable(monkeypatch):
    from engine.turnos_ollama import elegir_area_y_nivel
    for basura in ('{"area": "otra", "nivel": "ligero"}', "no es json", "{}"):
        _fingir_capitan(monkeypatch, basura)
        assert elegir_area_y_nivel("x").seguro is False, basura


def test_el_capitan_restringe_la_salida_con_esquema(monkeypatch):
    """Decodificacion restringida, no confianza en la obediencia.

    Confirmado en vivo el 2026-09-16: nemotron-mini ignoraba «responde SOLO con
    la etiqueta» y contestaba la pregunta del usuario, alucinando nombres de
    agentes inexistentes.
    """
    import engine.turnos_ollama as mod
    visto = {}
    monkeypatch.setattr(mod, "run_with_tools",
                        lambda **k: (visto.update(k),
                                     '{"area":"codigo","nivel":"ligero"}')[1])
    mod.elegir_area_y_nivel("escribe f(x)")
    esquema = visto.get("format_schema")
    assert esquema, "el capitan invoco sin format_schema"
    assert esquema["properties"]["area"]["enum"] == list(mod.AREAS)
    assert esquema["properties"]["nivel"]["enum"] == list(mod.NIVELES)


def test_el_capitan_no_recibe_ventana_grande(monkeypatch):
    """Clasificar no pide contexto profundo, y nemotron-mini tiene 4.096."""
    import engine.turnos_ollama as mod
    visto = {}
    monkeypatch.setattr(mod, "run_with_tools",
                        lambda **k: (visto.update(k),
                                     '{"area":"codigo","nivel":"ligero"}')[1])
    mod.elegir_area_y_nivel("x")
    assert visto["num_ctx"] <= 4096, visto["num_ctx"]
