"""Tests del verificador. La derivación de casos va inyectada: sin Ollama.

Los tres códigos de abajo son los que el Concilio produjo REALMENTE el
2026-09-24 para el mismo encargo, puntuándose 92, 93 y 96. Ninguno funciona.
Si el verificador no los suspende, no sirve para nada.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.verificador import (  # noqa: E402
    Caso,
    derivar_casos,
    ejecutar_verificacion,
    verificar,
)

# ─── los tres códigos reales ──────────────────────────────────────────────────

ROTO_1 = '''import re
def validar_token_telegram(token: str) -> bool:
    patron = r"^[0-9]+\\.\\w{35}$"
    return bool(re.match(patron, token))
'''

ROTO_2 = '''import re
def validar_token_telegram(token: str) -> bool:
    patron = r"^\\d+\\.\\w{35}$"
    if re.match(patron, token):
        return True
    return False
'''

ROTO_3 = '''def validar_token_telegram(token: str) -> bool:
    if len(token) != 35:
        return False
    if not token.replace("-", "").replace("_", "").isdigit():
        return False
    return True
'''

CORRECTO = '''import re
def validar_token_telegram(token: str) -> bool:
    return bool(re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{35}", token))
'''

# Casos como los derivaría del enunciado: 4 válidos, 4 inválidos.
CASOS = [
    Caso('validar_token_telegram("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo")',
         "True", "identificador, dos puntos, 35 caracteres"),
    Caso('validar_token_telegram("8460857489:AAHD_t4GAFOuPXXs5p022EddxDSC67e7vVw")',
         "True", "el guion bajo esta en el alfabeto"),
    Caso('validar_token_telegram("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")',
         "True", "identificador mas corto, secreto de 35"),
    Caso('validar_token_telegram("99:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")',
         "True", "identificador de dos digitos"),
    Caso('validar_token_telegram("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdoX")',
         "False", "36 caracteres viola EXACTAMENTE 35"),
    Caso('validar_token_telegram("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUd")',
         "False", "34 caracteres viola EXACTAMENTE 35"),
    Caso('validar_token_telegram("8460857489.AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo")',
         "False", "el separador son DOS PUNTOS, no un punto"),
    Caso('validar_token_telegram("abc:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo")',
         "False", "el identificador es numerico"),
]


# ─── lo que el árbitro no pudo ver ────────────────────────────────────────────

def test_suspende_los_tres_codigos_que_el_arbitro_aprobo():
    """92, 93 y 96 de autoscore. Ninguno funciona."""
    for etiqueta, codigo in (("roto_1", ROTO_1), ("roto_2", ROTO_2), ("roto_3", ROTO_3)):
        v = ejecutar_verificacion(codigo, CASOS)
        assert v.error is None, f"{etiqueta}: {v.error}"
        assert v.puntuacion < 85, (
            f"{etiqueta} saca {v.puntuacion}% y el arbitro le puso >90")


def test_aprueba_el_codigo_correcto():
    v = ejecutar_verificacion(CORRECTO, CASOS)
    assert v.error is None
    assert v.puntuacion == 100
    assert v.supera_la_base


def test_detecta_que_no_supera_la_base_trivial():
    """Los tres rotos rechazan casi todo: aciertan los negativos por omision.

    Con un conjunto desbalanceado eso pareceria competencia --- error que
    cometi montando la primera vara de medir.
    """
    for codigo in (ROTO_1, ROTO_2, ROTO_3):
        v = ejecutar_verificacion(codigo, CASOS)
        assert not v.supera_la_base, "un rechaza-todo no debe superar la base"


def test_el_separador_equivocado_queda_señalado():
    v = ejecutar_verificacion(ROTO_1, CASOS)
    fallidos = [f for f in v.detalle if not f["correcto"]]
    assert fallidos, "debe haber fallos"
    # los cuatro tokens válidos deben aparecer como fallo
    assert sum(1 for f in fallidos if f["esperado"] == "True") == 4


# ─── aislamiento ──────────────────────────────────────────────────────────────

def test_un_bucle_infinito_no_cuelga_el_verificador():
    codigo = "def f():\n    while True:\n        pass\n"
    v = ejecutar_verificacion(codigo, [Caso("f()", "None")], limite_segundos=3)
    assert v.error and "no termina" in v.error


def test_codigo_que_no_compila_se_reporta_sin_reventar():
    v = ejecutar_verificacion("def roto(:\n  pass", [Caso("roto()", "None")])
    assert v.error and "no compila" in v.error


def test_una_excepcion_en_un_caso_no_tumba_los_demas():
    codigo = "def f(x):\n    if x == 0:\n        raise ValueError('no')\n    return x\n"
    v = ejecutar_verificacion(codigo, [Caso("f(0)", "0"), Caso("f(5)", "5")])
    assert v.error is None
    assert v.aciertos == 1
    assert any("EXCEPCION" in f["obtenido"] for f in v.detalle)


def test_la_red_esta_cerrada_dentro_del_verificador():
    codigo = ("import socket\n"
              "def f():\n"
              "    try:\n"
              "        socket.socket()\n"
              "        return 'ABRIO'\n"
              "    except Exception:\n"
              "        return 'BLOQUEADA'\n")
    v = ejecutar_verificacion(codigo, [Caso("f()", "'BLOQUEADA'")])
    assert v.aciertos == 1, "el verificador debe cerrar la red al codigo"


def test_exit_dentro_del_codigo_no_se_lleva_al_orquestador():
    v = ejecutar_verificacion("import sys\ndef f():\n    sys.exit(1)\n",
                              [Caso("f()", "None")])
    assert v.error is not None or v.aciertos == 0


# ─── el orden: casos DEL ENUNCIADO, no de la solución ─────────────────────────

def test_el_modelo_que_deriva_casos_no_ve_el_codigo():
    """Si viera la solucion, ancraria las pruebas a lo que hace --- y aprobaria
    el mismo error que debia cazar."""
    visto = {}

    def invocar(prompt):
        visto["prompt"] = prompt
        return json.dumps([{"entrada": 'validar_token_telegram("a:b")',
                            "esperado": "False", "porque": "prueba"}])

    verificar("el enunciado", ROTO_1, invocar)
    assert "el enunciado" in visto["prompt"]
    assert "re.match" not in visto["prompt"], "el codigo se colo en el prompt"
    assert "patron" not in visto["prompt"]


def test_el_prompt_pide_casos_no_soluciones():
    from engine.verificador import PROMPT_CASOS
    assert "NO resuelvas el enunciado" in PROMPT_CASOS
    assert "NO escribas la implementación" in PROMPT_CASOS


def test_casos_ilegibles_no_revientan():
    v, casos = verificar("x", ROTO_1, lambda p: "no hay json aqui")
    assert casos == []
    assert v.error and "JSON" in v.error


def test_sin_casos_la_puntuacion_es_cero_no_cien():
    """No verificable != verificado y correcto."""
    v, _ = verificar("x", ROTO_1, lambda p: "[]")
    assert v.puntuacion == 0


def test_los_casos_llevan_la_frase_que_los_justifica():
    """Sin el 'porque', un caso discutible no se puede auditar."""
    casos, err = derivar_casos(
        "enunciado",
        lambda p: json.dumps([{"entrada": "f(1)", "esperado": "1",
                               "porque": "el enunciado dice que f(1)=1"}]),
    )
    assert err is None
    assert casos[0].porque


# ─── el cableado: la ejecución manda sobre la lectura ─────────────────────────

def _blackboard_con(codigo, enunciado):
    from memory.blackboard import Blackboard, CodeArtifact
    bb = Blackboard(task_id="t", session_id="s", user_prompt=enunciado)
    bb.code_proposal = CodeArtifact(language="python", code=codigo,
                                    raw_content=codigo)
    return bb


ENUNCIADO = ("Escribe validar_token_telegram(token) que devuelva True solo si el "
             "token tiene identificador numerico, DOS PUNTOS, y un secreto de "
             "EXACTAMENTE 35 caracteres del alfabeto [A-Za-z0-9_-].")


def _arbitro_falso(score_leido, casos_json):
    """Árbitro que LEE y pone `score_leido`, y que deriva `casos_json`."""
    from agents.optimizer import OptimizerAgent
    a = OptimizerAgent.__new__(OptimizerAgent)
    a.name = "arbitro"
    llamadas = []

    def generate(prompt, system_override=None, stream_callback=None):
        llamadas.append((prompt, system_override))
        if system_override:                       # derivando casos
            return casos_json
        return f"auditoria leida [PUNTUACION_CONSENSO: {score_leido}]"

    a.generate = generate
    a._llamadas = llamadas
    return a


CASOS_JSON = json.dumps([
    {"entrada": 'validar_token_telegram("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo")',
     "esperado": "True", "porque": "dos puntos y 35 caracteres"},
    {"entrada": 'validar_token_telegram("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")',
     "esperado": "True", "porque": "identificador mas corto"},
    {"entrada": 'validar_token_telegram("8460857489.AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo")',
     "esperado": "False", "porque": "el separador son DOS PUNTOS"},
    {"entrada": 'validar_token_telegram("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdoX")',
     "esperado": "False", "porque": "36 viola EXACTAMENTE 35"},
])


def test_la_ejecucion_corrige_al_arbitro_que_aprobaba_codigo_roto():
    """El escenario real del 2026-09-24: leyendo puso 96 a roto_3."""
    from memory.shared_context import SharedMemory
    a = _arbitro_falso(96, CASOS_JSON)
    sm = SharedMemory.__new__(SharedMemory)
    sm.active_blackboard = _blackboard_con(ROTO_3, ENUNCIADO)
    sm.research_context = None

    art = a.evaluate_solution(sm, threshold=85, espera_codigo=True)
    assert art.score < 85, f"el arbitro seguiria aprobando con {art.score}"
    assert art.score != 96, "el score debe venir de la ejecucion, no de la lectura"


def test_el_codigo_correcto_sigue_aprobando():
    from memory.shared_context import SharedMemory
    a = _arbitro_falso(60, CASOS_JSON)   # el arbitro lo suspende LEYENDO
    sm = SharedMemory.__new__(SharedMemory)
    sm.active_blackboard = _blackboard_con(CORRECTO, ENUNCIADO)
    sm.research_context = None

    art = a.evaluate_solution(sm, threshold=85, espera_codigo=True)
    assert art.score == 100, "la ejecucion debe rescatar codigo bueno mal leido"


def test_el_que_deriva_casos_no_recibe_el_codigo():
    from memory.shared_context import SharedMemory
    a = _arbitro_falso(96, CASOS_JSON)
    sm = SharedMemory.__new__(SharedMemory)
    sm.active_blackboard = _blackboard_con(ROTO_3, ENUNCIADO)
    sm.research_context = None
    a.evaluate_solution(sm, threshold=85, espera_codigo=True)

    derivacion = [p for p, sysov in a._llamadas if sysov]
    assert derivacion, "no hubo derivacion de casos"
    assert "isdigit" not in derivacion[0], "el codigo se colo en el prompt de casos"
    assert "len(token)" not in derivacion[0]


def test_sin_casos_derivables_se_conserva_la_lectura_pero_queda_anotado():
    """No verificable no es lo mismo que verificado y correcto."""
    from memory.shared_context import SharedMemory
    a = _arbitro_falso(90, "no hay json")
    sm = SharedMemory.__new__(SharedMemory)
    sm.active_blackboard = _blackboard_con(ROTO_3, ENUNCIADO)
    sm.research_context = None
    art = a.evaluate_solution(sm, threshold=85, espera_codigo=True)
    assert art.score == 90, "sin verificacion posible se conserva la lectura"
    eventos = [e for e in sm.active_blackboard.execution_timeline
               if e.get("stage") == "VERIFY"]
    assert eventos and "no verificable" in eventos[-1]["message"]


def test_en_tareas_sin_codigo_no_se_verifica():
    from memory.shared_context import SharedMemory
    a = _arbitro_falso(78, CASOS_JSON)
    sm = SharedMemory.__new__(SharedMemory)
    bb = _blackboard_con(ROTO_3, ENUNCIADO)
    bb.code_proposal = None
    sm.active_blackboard = bb
    sm.research_context = None
    art = a.evaluate_solution(sm, threshold=85, espera_codigo=False)
    assert art.score == 78
    assert not [p for p, sysov in a._llamadas if sysov], "no debio derivar casos"


# ─── EL AGUJERO DEL 2026-09-24: no verificado colandose como aprobado ────────
# El arbitro puntuaba con la EJECUCION cuando podia ejecutar, y con la LECTURA
# cuando no. Pero nada distinguia los dos casos aguas abajo: una ronda en la
# que el verificador no lograba derivar casos caia al score de lectura --- 92,
# 93, 96 en las tres corridas medidas --- y ese numero cruzaba el umbral de 85
# sin que nadie hubiera ejecutado una linea. Quedaba anotado en la pizarra y no
# frenaba nada.

def _pizarra(prompt="Escribe una funcion f(x) que devuelva x+1"):
    from memory.blackboard import Blackboard
    return Blackboard(task_id="t", session_id="s", user_prompt=prompt)


def test_no_verificado_no_declara_consenso():
    """Score por encima del umbral, pero nadie ejecuto: NO es consenso."""
    bb = _pizarra()
    c = bb.add_critique("da igual", score=96, threshold=85,
                        verificado_por_ejecucion=False)
    assert c.score == 96
    assert not c.passed, "96 leido no puede declarar consenso"
    assert not bb.consensus_reached
    # y tiene que DECIRLO, no callarlo
    assert any("LEER" in e["message"] for e in bb.execution_timeline)


def test_verificado_por_ejecucion_si_declara_consenso():
    """Mismo score, pero ejecutado: ahi si cierra."""
    bb = _pizarra()
    c = bb.add_critique("da igual", score=96, threshold=85,
                        verificado_por_ejecucion=True)
    assert c.passed and bb.consensus_reached


def test_sin_codigo_esperado_no_se_exige_ejecucion():
    """Una auditoria o un analisis no lleva codigo: None no debe bloquear."""
    bb = _pizarra("Audita este proyecto y dame hallazgos")
    c = bb.add_critique("hallazgos", score=90, threshold=85,
                        verificado_por_ejecucion=None)
    assert c.passed and bb.consensus_reached


def test_no_verificado_bajo_el_umbral_sigue_refinando():
    """Sin verificar y por debajo: refina, y sin el aviso enganoso."""
    bb = _pizarra()
    c = bb.add_critique("flojo", score=40, threshold=85,
                        verificado_por_ejecucion=False)
    assert not c.passed
    assert not any("alcanza el umbral" in e["message"] for e in bb.execution_timeline)
