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


def test_quince_de_dieciseis_no_es_verificado():
    """ACEPTACION v1, 2026-09-25: es_matricula salio VERIFICADO con 15/16.

    15/16 con base 8 son 88% sobre la base, por encima de 85, y el codigo
    aceptaba '!OV-3074'. Con casos de especificacion cada caso es un requisito:
    fallar uno es violar el enunciado.
    """
    uno_fallado = _veredicto(15, 16, 8, fallos=["es_matricula('!OV-3074')"])
    orq, prompts = _orquestador([uno_fallado, uno_fallado])
    bb = Blackboard(task_id="t", session_id="s", user_prompt=(
        "Escribe una funcion Python llamada es_matricula(s: str) -> bool con "
        "tres letras mayusculas, un guion y cuatro digitos."))
    assert orq._intentar_via_directa(bb) == "concilio"
    assert not bb.consensus_reached
    assert "es_matricula('!OV-3074')" in prompts[1], "el segundo intento debe saber cual fallo"


# ─── MEJOR INTENTO MEDIDO ─────────────────────────────────────────────────────
# Aceptacion v1, 2.a pasada: es_matricula dio 15/16 por la via directa, el
# concilio lo EMPEORO a 8/16 en tres rondas, y se entrego el 8/16.

def test_se_guarda_el_mejor_no_el_ultimo():
    bb = _pizarra()
    O = ConsensusOrchestrator
    O._registrar_intento(bb, 15, 16, "def a(): pass", ["x"], "via directa, intento 1")
    O._registrar_intento(bb, 8, 16, "def b(): pass", ["y"] * 8, "concilio, ronda 1")
    assert bb.shared_notes["mejor_intento"]["aciertos"] == 15
    assert bb.shared_notes["mejor_intento"]["origen"] == "via directa, intento 1"


def test_sin_consenso_se_entrega_el_mejor_rotulado():
    bb = _pizarra()
    ConsensusOrchestrator._registrar_intento(
        bb, 15, 16, "def es_matricula(s): return True", ["es_matricula('!OV-3074')"],
        "via directa, intento 1")
    bb.final_synthesis = "sintesis del concilio con el codigo de 8/16"
    assert ConsensusOrchestrator._entregar_mejor_intento(bb) is True
    assert "15/16" in bb.final_synthesis
    assert "es_matricula('!OV-3074')" in bb.final_synthesis, "tiene que decir que falla"
    assert "def es_matricula" in bb.final_synthesis
    assert not bb.consensus_reached, "entregar el mejor NO es aprobarlo"


def test_con_consenso_no_se_toca_la_entrega():
    bb = _pizarra()
    ConsensusOrchestrator._registrar_intento(bb, 15, 16, "def x(): pass", [], "o")
    bb.consensus_reached = True
    bb.final_synthesis = "la verificada"
    assert ConsensusOrchestrator._entregar_mejor_intento(bb) is False
    assert bb.final_synthesis == "la verificada"


def test_la_via_directa_registra_sus_intentos():
    f = _veredicto(15, 16, 8, fallos=["es_matricula('!OV-3074')"])
    orq, _ = _orquestador([f, f])
    bb = _pizarra()
    orq._intentar_via_directa(bb)
    mejor = bb.shared_notes.get("mejor_intento")
    assert mejor and mejor["aciertos"] == 15 and "via directa" in mejor["origen"]


def test_el_mejor_intento_no_entra_en_el_contexto_del_coder():
    """Lleva codigo; mas contexto le mueve la salida al coder (medido)."""
    bb = _pizarra()
    ConsensusOrchestrator._registrar_intento(bb, 15, 16, "def SECRETO_DEL_MEJOR(): pass",
                                             [], "o")
    bb.shared_notes["ultimo_veredicto"] = {"codigo": "def SECRETO_DEL_ULTIMO(): pass"}
    ctx = bb.get_context_for_coder()
    assert "SECRETO_DEL_MEJOR" not in ctx and "SECRETO_DEL_ULTIMO" not in ctx


def test_el_segundo_intento_usa_el_modelo_de_respaldo():
    """Con modelo_segundo_intento configurado, el 2º intento usa ese modelo."""
    fallo = _veredicto(11, 16, 8, fallos=["validar_token_telegram('0:AHOV_x')"])
    orq, prompts = _orquestador([fallo, _veredicto(16, 16, 8)])
    # Simula el atributo que __init__ pondria
    orq._modelo_segundo_intento = "qwen2.5-coder:7b"
    # Mock del coder de respaldo
    modelos_usados = []
    coder_respaldo = NS(model="qwen2.5-coder:7b", name="Coder respaldo",
                        generate=lambda prompt: (modelos_usados.append("respaldo"), CODIGO)[1])
    orq._coder_respaldo = lambda: coder_respaldo
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "verificado"
    # Intento 1 va al coder principal (prompts), intento 2 al respaldo (modelos_usados)
    assert len(prompts) == 1
    assert modelos_usados == ["respaldo"], "el 2º intento debe usar el coder de respaldo"


def test_sin_modelo_de_respaldo_repite_el_coder():
    """Sin modelo_segundo_intento (v1), el 2º intento repite el coder principal."""
    fallo = _veredicto(11, 16, 8, fallos=["validar_token_telegram('0:AHOV_x')"])
    orq, prompts = _orquestador([fallo, _veredicto(16, 16, 8)])
    # Sin _modelo_segundo_intento -> _coder_respaldo devuelve None
    orq._modelo_segundo_intento = ""
    bb = _pizarra()
    assert orq._intentar_via_directa(bb) == "verificado"
    # Ambos intentos usan el coder principal -> 2 prompts
    assert len(prompts) == 2, "ambos intentos usan el coder principal"
