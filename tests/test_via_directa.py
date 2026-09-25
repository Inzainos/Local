"""Pruebas de la via directa: una llamada al coder, verificar, y concilio solo si falla.

Medido el 2026-09-25: codegemma resolvio 6 de 7 tareas a la primera en ~30 s;
el concilio tardo 25-50 min y no cerro ninguna. Aqui se fija el control de
flujo, sin red.
"""
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.orchestrator import ConsensusOrchestrator  # noqa: E402
from engine.verificador import Veredicto  # noqa: E402
from memory.blackboard import Blackboard  # noqa: E402

TOKEN = ("Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool "
         "que acepte identificador numerico, DOS PUNTOS y un secreto de 35 caracteres.")
CODIGO = "```python\ndef validar_token_telegram(token):\n    return True\n```"


def _veredicto(aciertos, total, base, via="especificacion", error=None, fallos=()):
    v = Veredicto(aciertos, total, linea_base=base, error=error,
                  detalle=[{"entrada": e, "obtenido": "False", "esperado": "True",
                            "correcto": False} for e in fallos])
    v.via = via
    return v


def _orquestador(veredictos, respuestas=None, sin_verificacion="entregar"):
    orq = ConsensusOrchestrator.__new__(ConsensusOrchestrator)
    orq.threshold, orq._intentos_directos = 85, 2
    orq._sin_verificacion = sin_verificacion
    prompts = []
    respuestas = list(respuestas or [CODIGO] * 4)
    coder = NS(model="codegemma:7b", name="Coder directo",
               generate=lambda prompt: (prompts.append(prompt), respuestas.pop(0))[1])
    orq._coder_directo = lambda: coder
    orq._run_exclusive = lambda model, fn, *a, **k: fn()
    cola = list(veredictos)
    orq.optimizer = NS(_verificar_ejecutando=lambda bb: (cola.pop(0), []))
    return orq, prompts


def _pizarra(prompt=TOKEN):
    return Blackboard(task_id="t", session_id="s", user_prompt=prompt)


def test_verificado_a_la_primera_se_entrega_sin_concilio():
    orq, prompts = _orquestador([_veredicto(16, 16, 8)])
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "verificado"
    assert len(prompts) == 1, "no hacia falta un segundo intento"
    assert bb.consensus_reached and bb.shared_notes["via"] == "directa_verificada"
    assert "def validar_token_telegram" in bb.final_synthesis
    assert bb.consensus_score == 100


def test_el_segundo_intento_recibe_los_casos_fallidos():
    fallo = _veredicto(11, 16, 8, fallos=["validar_token_telegram('0:AHOV_x')"])
    orq, prompts = _orquestador([fallo, _veredicto(16, 16, 8)])
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "verificado"
    assert len(prompts) == 2
    assert "validar_token_telegram('0:AHOV_x')" in prompts[1], (
        "el segundo intento tiene que saber que caso fallo")
    assert "FALLO" in prompts[1]


def test_si_falla_con_casos_fiables_pasa_al_concilio():
    f = _veredicto(11, 16, 8, fallos=["x"])
    orq, _ = _orquestador([f, f])
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "concilio"
    assert not bb.consensus_reached


def test_sin_verificacion_fiable_se_entrega_rotulado_sin_reintentar():
    """Casos derivados: no aprueban, y no se reintenta con ellos (pueden estar mal)."""
    orq, prompts = _orquestador([_veredicto(8, 8, 4, via="derivados")])
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "sin_verificacion"
    assert len(prompts) == 1, "se reintento con casos que pueden tener el esperado mal"
    assert not bb.consensus_reached, "SIN VERIFICAR no puede figurar como aprobado"
    assert bb.shared_notes["via"] == "directa_sin_verificar"
    assert "SIN VERIFICAR" in bb.final_synthesis


def test_sin_verificacion_fiable_puede_configurarse_hacia_el_concilio():
    orq, _ = _orquestador([_veredicto(8, 8, 4, via="derivados")], sin_verificacion="concilio")
    assert orq._intentar_via_directa(_pizarra()) == "concilio"


def test_un_enunciado_sin_funcion_va_al_concilio():
    orq, prompts = _orquestador([])
    assert orq._intentar_via_directa(_pizarra("Audita el repositorio")) == "concilio"
    assert prompts == [], "no se debe llamar al coder sin funcion que verificar"


def test_sin_codigo_en_la_respuesta_se_reintenta_diciendoselo():
    sin_codigo = _veredicto(0, 0, 0, error="la respuesta no contiene un bloque de "
                                            "codigo con la funcion pedida")
    orq, prompts = _orquestador([sin_codigo, _veredicto(16, 16, 8)],
                                respuestas=["no se hacerlo", CODIGO])
    assert orq._intentar_via_directa(_pizarra()) == "verificado"
    assert "no contiene un bloque de codigo" in prompts[1]


def test_un_conjunto_que_no_discrimina_no_aprueba():
    """7/8 con base 7/8: el 88% de la noche del 24. Nunca mas."""
    orq, _ = _orquestador([_veredicto(7, 8, 7), _veredicto(7, 8, 7)])
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "concilio"
    assert not bb.consensus_reached
