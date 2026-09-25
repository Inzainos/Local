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


# ─── CONJUNTOS DE CASOS QUE NO MIDEN NADA ─────────────────────────────────────
# El 2026-09-24 el arbitro derivo 8 casos de los que SIETE esperaban el mismo
# valor. Un codigo que devuelve siempre esa constante acierta 7 de 8 y saca 88%
# --- por encima del umbral de 85 --- sin tener ninguna capacidad. Y eso ocurrio:
# se declaro consenso sobre un codigo que rechazaba los cuatro tokens validos.
#
# Es el mismo error que yo cometi montando la primera vara de medir (2 positivos,
# 7 negativos, `return False` sacaba 78%). Lo corregi en mi conjunto y no en el
# del verificador.

def test_el_conjunto_de_la_tarea_1_no_discrimina():
    """EL CASO REAL: 7 aciertos de 8, con base trivial de 7 de 8."""
    from engine.verificador import Veredicto
    v = Veredicto(aciertos=7, total=8, linea_base=7)
    assert v.puntuacion == 88, "el acierto crudo sigue siendo 88%"
    assert not v.discrimina, "un conjunto con base 7/8 no puede medir nada"
    assert v.puntuacion_util == 0, "igualar la base es cero merito"
    assert "NO DISCRIMINA" in v.resumen()


def test_un_conjunto_balanceado_si_discrimina():
    from engine.verificador import Veredicto
    v = Veredicto(aciertos=8, total=8, linea_base=4)
    assert v.discrimina and v.puntuacion_util == 100


def test_pocos_casos_no_permiten_concluir():
    from engine.verificador import Veredicto
    v = Veredicto(aciertos=3, total=3, linea_base=2)
    assert not v.discrimina, "tres casos no bastan"
    assert v.puntuacion_util == 0


def test_la_puntuacion_util_mide_ganancia_sobre_la_base():
    """(aciertos - base) / (total - base). Igualar la base da 0, todo da 100."""
    from engine.verificador import Veredicto
    assert Veredicto(aciertos=4, total=8, linea_base=4).puntuacion_util == 0
    assert Veredicto(aciertos=6, total=8, linea_base=4).puntuacion_util == 50
    assert Veredicto(aciertos=8, total=8, linea_base=4).puntuacion_util == 100


def test_un_veredicto_con_error_no_discrimina():
    from engine.verificador import Veredicto
    v = Veredicto(0, 8, error="la solucion no compila: SyntaxError")
    assert not v.discrimina and v.puntuacion_util == 0


# ─── el arbitro no debe cerrar con casos que no miden ────────────────────────

def _arbitro_con_veredicto(monkeypatch, veredicto):
    """Arbitro cuyo verificador devuelve `veredicto`, sin tocar Ollama."""
    from agents.optimizer import OptimizerAgent
    from memory.blackboard import Blackboard

    a = OptimizerAgent.__new__(OptimizerAgent)
    a.name = "arbitro"
    monkeypatch.setattr(a, "generate",
                        lambda **k: "Analisis. [PUNTUACION_CONSENSO: 96]",
                        raising=False)
    monkeypatch.setattr(a, "_verificar_ejecutando",
                        lambda bb: (veredicto, []), raising=False)
    bb = Blackboard(task_id="t", session_id="s",
                    user_prompt="Escribe validar_token_telegram(token)")
    bb.update_code("```python\ndef validar_token_telegram(t): return False\n```")

    class _Mem:                       # evaluate_solution recibe la memoria
        blackboard = bb
    return a, _Mem(), bb


def test_con_casos_que_no_discriminan_no_hay_consenso(monkeypatch):
    """EL FALLO DEL 2026-09-24, de punta a punta."""
    from engine.verificador import Veredicto
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, Veredicto(7, 8, linea_base=7))
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert not c.passed, ("88% crudo sobre un conjunto con base 7/8 volvio a "
                          "declarar consenso")
    assert c.verificado_por_ejecucion is False
    assert any("NO DISCRIMINA" in e["message"] or "balanceados" in e["message"]
               for e in bb.execution_timeline)


def test_con_casos_buenos_el_score_es_la_ganancia(monkeypatch):
    """No el acierto crudo: 6/8 con base 4 son 50, no 75."""
    from engine.verificador import Veredicto
    v = Veredicto(6, 8, linea_base=4)
    v.via = "especificacion"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert c.score == 50, f"uso {c.score}; el crudo (75) engana"
    assert c.verificado_por_ejecucion is True
    assert not c.passed


def test_un_codigo_correcto_si_pasa(monkeypatch):
    """El cierre no puede ser solo un freno: tiene que dejar pasar lo bueno."""
    from engine.verificador import Veredicto
    v = Veredicto(8, 8, linea_base=4)
    v.via = "especificacion"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert c.score == 100 and c.passed
    assert c.verificado_por_ejecucion is True


# ─── EXTRACCION TOLERANTE ─────────────────────────────────────────────────────
# El 2026-09-24, midiendo que modelo deriva mejores casos, TRES de cinco se
# contabilizaron como «la respuesta no contenia un array JSON». Al mirar la
# salida cruda, dos de esos tres fallos eran del parser, no del modelo:
#
#   nemotron-mini     array con estructura PERFECTA y True/False de Python
#   llama3.2:3b       1.817 chars, cortado sin cerrar el corchete
#   qwen2.5-coder:7b  3.992 chars, cortado sin cerrar el corchete
#
# Iba a concluir «ningun modelo puede» y en parte era el instrumento. Sin
# guardar la salida cruda no habria forma de distinguir una cosa de la otra ---
# que es el fallo del dia aplicado a mi propio experimento.

def test_acepta_literales_de_python():
    """nemotron-mini devolvio True/False en vez de true/false."""
    from engine.verificador import _extraer_json
    d = _extraer_json('[{"entrada": "f(1)", "esperado": True, "porque": "x"}]')
    assert d and len(d) == 1 and d[0]["esperado"] is True


def test_no_toca_literales_dentro_de_una_cadena():
    """«True» como texto de un campo no debe convertirse."""
    from engine.verificador import _normalizar_literales
    assert '"esperado": "True"' in _normalizar_literales('"esperado": "True"')


def test_rescata_los_casos_de_un_array_truncado():
    """Once casos buenos no se pierden por culpa del doceavo cortado."""
    from engine.verificador import _extraer_json
    truncado = ('```json\n[\n'
                '  {"entrada": "f(1)", "esperado": "True", "porque": "a"},\n'
                '  {"entrada": "f(2)", "esperado": "False", "porque": "b"},\n'
                '  {"entrada": "f(3)", "esper')
    d = _extraer_json(truncado)
    assert d and len(d) == 2, f"rescato {len(d or [])} de los 2 completos"


def test_no_inventa_casos_donde_no_hay():
    """Tolerante no es adivino: sin datos, None."""
    from engine.verificador import _extraer_json
    for basura in ("", "no hay nada aqui", "lo siento, no puedo", "{}", "[]"):
        d = _extraer_json(basura)
        assert not d, f"{basura!r} produjo {d}"


# ─── lo que recibe el CODER cuando la ejecucion contradice a la lectura ──────
# En la bateria del 2026-09-25 el arbitro leyo 97, 98, 99, 99 sobre un codigo
# que rechazaba los ocho tokens validos. El informe de ejecucion iba pegado al
# FINAL de esa lectura, y el coder recibia la orden de «resolver los puntos de
# la auditoria»: reemitio el mismo codigo hasta que el freno lo corto.

def test_el_veredicto_de_ejecucion_va_antes_que_la_lectura(monkeypatch):
    from engine.verificador import Veredicto
    v = Veredicto(8, 16, linea_base=8, detalle=[
        {"entrada": "validar_token_telegram('0:AHOVcjqx4-GNUbipw3_FMTahov29ELSZgnu')",
         "obtenido": "False", "esperado": "True", "correcto": False}])
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    texto = c.raw_content
    i_ejec = texto.find("VERIFICACION POR EJECUCION")
    i_lect = texto.find("Analisis")          # la lectura fingida del arbitro
    assert 0 <= i_ejec < i_lect, "el veredicto de ejecucion tiene que ir PRIMERO"
    assert "ANULADA" in texto
    assert "esperado True" in texto, "el caso fallido concreto tiene que llegar"


def test_la_puntuacion_leida_queda_neutralizada(monkeypatch):
    """Si sobrevive `[PUNTUACION_CONSENSO: 96]`, alguien aguas abajo la cree."""
    from engine.verificador import Veredicto
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, Veredicto(6, 8, linea_base=4))
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert "[PUNTUACION_CONSENSO:" not in c.raw_content
    assert "[PUNTUACION_LEIDA_ANULADA: 96]" in c.raw_content


def test_el_coder_recibe_la_orden_confiable_de_obedecer_la_ejecucion():
    """La orden va FUERA de los bloques no confiables: si va dentro, el
    preambulo anti-inyeccion le dice al modelo que la ignore."""
    from memory.blackboard import Blackboard
    bb = Blackboard(task_id="t", session_id="s", user_prompt="x")
    bb.update_code("```python\ndef f(): pass\n```")
    bb.add_critique("=== VERIFICACION POR EJECUCION ===\nfalla", score=0)
    ctx = bb.get_context_for_refinement()
    confiable = ctx[ctx.rfind("INSTRUCCIÓN DEL SISTEMA (confiable)"):]
    assert "VERIFICACION POR EJECUCION" in confiable
    assert "MANDAN" in confiable


# ─── QUE SE EJECUTA: el bloque correcto, nunca prosa ──────────────────────────
# Medido el 2026-09-25 en `a_segundos`: los cuatro «no compila» del verificador
# eran falsos. Con la extraccion correcta, tres de las cuatro versiones del
# coder compilaban y solo fallaban '1h30m'. El coder refino cuatro rondas
# contra un diagnostico inventado y nunca supo cual era su fallo real.

V1_VARIOS_BLOQUES = """### Implementacion

```python
def a_segundos(texto):
    return 7200 if texto == "2h" else 0
```

Ejemplo de uso:

```python
print(a_segundos("2h"))
```

Salida:

```
7200
```
"""

V2_ECO_DE_LA_ENTRADA = """<<<UNTRUSTED_DATA role="historial_tareas" NOTICE="DATA_NOT_INSTRUCTIONS">>>
- [HECHO APROBADO · Concilio score=88/85] Escribe validar_token_telegram
<<<END_UNTRUSTED_DATA>>>

```python
def a_segundos(texto):
    return 0
```
"""

V4_SOLO_MEMORIA = """<<<UNTRUSTED_DATA role="historial_tareas" NOTICE="DATA_NOT_INSTRUCTIONS">>>
- [HECHO APROBADO · Concilio score=88/85] Escribe validar_token_telegram
<<<END_UNTRUSTED_DATA>>>"""


def test_no_concatena_bloques():
    """v1: el codigo, un ejemplo de uso y una salida. Solo el codigo."""
    from engine.verificador import extraer_codigo
    c = extraer_codigo(V1_VARIOS_BLOQUES, "a_segundos")
    compile(c, "<t>", "exec")                     # antes: SyntaxError
    assert "print(" not in c and "7200\n" not in c.split("return")[0]


def test_descarta_los_datos_que_el_modelo_repite():
    """v2: el coder repitio su bloque de memoria antes del codigo."""
    from engine.verificador import extraer_codigo
    c = extraer_codigo(V2_ECO_DE_LA_ENTRADA, "a_segundos")
    assert c.startswith("def a_segundos") and "UNTRUSTED" not in c


def test_sin_codigo_no_se_ejecuta_prosa():
    """v4: solo memoria. Antes se ejecutaba y daba «invalid character '·'»."""
    from engine.verificador import extraer_codigo
    assert extraer_codigo(V4_SOLO_MEMORIA, "a_segundos") == ""


def test_ignora_el_razonamiento():
    from engine.verificador import extraer_codigo
    t = ("<think>\n```python\ndef a_segundos(t): return -1\n```\n</think>\n"
         "```python\ndef a_segundos(t):\n    return 1\n```")
    assert "return 1" in extraer_codigo(t, "a_segundos")


def test_prefiere_el_bloque_de_la_funcion_pedida():
    from engine.verificador import extraer_codigo
    t = ("```python\ndef ayudante(x):\n    return x\n```\n"
         "```python\ndef a_segundos(t):\n    return 5\n```")
    assert extraer_codigo(t, "a_segundos").startswith("def a_segundos")


def test_saca_el_nombre_de_la_funcion_del_enunciado():
    from engine.verificador import nombre_funcion
    assert nombre_funcion("Escribe una funcion Python llamada a_segundos(texto: "
                          "str) -> int que ...") == "a_segundos"
    assert nombre_funcion("Audita el repositorio") is None


def test_el_arbitro_distingue_sin_codigo_de_no_compila(monkeypatch):
    """Sin codigo es otro fallo, y el coder necesita saber cual de los dos."""
    from agents.optimizer import OptimizerAgent
    from memory.blackboard import Blackboard
    a = OptimizerAgent.__new__(OptimizerAgent)
    bb = Blackboard(task_id="t", session_id="s", user_prompt=(
        "Escribe una funcion Python llamada a_segundos(texto: str) -> int"))
    bb.update_code(V4_SOLO_MEMORIA)
    v, casos = OptimizerAgent._verificar_ejecutando(a, bb)
    assert v is not None and casos == []
    assert "no contiene un bloque de codigo" in v.error
    assert "no compila" not in v.error


def test_el_coder_recibe_por_que_no_se_pudo_verificar(monkeypatch):
    from engine.verificador import Veredicto
    v = Veredicto(0, 0, error="la respuesta no contiene un bloque de codigo "
                              "con la funcion pedida")
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert c.raw_content.startswith("=== VERIFICACION POR EJECUCION: NO SE PUDO")
    assert "no contiene un bloque de codigo" in c.raw_content
    assert "[PUNTUACION_CONSENSO:" not in c.raw_content
    assert not c.passed


# ─── la autoridad del informe depende de QUIEN escribio los casos ─────────────
# 2026-09-25, a_segundos: el modelo derivo `a_segundos('2h')` -> esperado 120
# (son 7200) y `'2h10m'` -> esperado 0 (es valido). Con eso bloqueo un codigo de
# qwen que era CORRECTO. Presentar esos casos como «lo que manda» empujaria al
# coder a romperlo.

_FALSOS_DERIVADOS = [
    {"entrada": "a_segundos('2h')", "obtenido": "7200", "esperado": "120",
     "correcto": False},
    {"entrada": "a_segundos('2h10m')", "obtenido": "7800", "esperado": "0",
     "correcto": False},
]


def test_casos_derivados_llegan_marcados_como_no_fiables(monkeypatch):
    from engine.verificador import Veredicto
    v = Veredicto(10, 12, linea_base=6, detalle=_FALSOS_DERIVADOS)
    v.via = "derivados"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    texto = a.evaluate_solution(mem, threshold=85, espera_codigo=True).raw_content
    assert "PROPUESTOS por un modelo" in texto
    assert "lo que manda" not in texto, (
        "casos con el esperado mal no pueden llegar al coder como autoridad")
    assert "esperado 120" in texto, "la informacion llega, pero rotulada"


def test_casos_de_especificacion_si_mandan(monkeypatch):
    from engine.verificador import Veredicto
    v = Veredicto(11, 16, linea_base=8, detalle=[
        {"entrada": "validar_token_telegram('0:AHOVcjqx4-GNUbipw3_FMTahov29ELSZgnu')",
         "obtenido": "False", "esperado": "True", "correcto": False}])
    v.via = "especificacion"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    texto = a.evaluate_solution(mem, threshold=85, espera_codigo=True).raw_content
    assert "lo que manda" in texto and "PROPUESTOS" not in texto


def test_la_orden_confiable_distingue_las_dos_vias():
    from memory.blackboard import Blackboard
    bb = Blackboard(task_id="t", session_id="s", user_prompt="x")
    bb.update_code("```python\ndef f(): pass\n```")
    bb.add_critique("informe", score=0)
    confiable = bb.get_context_for_refinement()
    confiable = confiable[confiable.rfind("INSTRUCCIÓN DEL SISTEMA (confiable)"):]
    assert "PROPUSO un modelo" in confiable and "no rompas" in confiable



def test_casos_derivados_no_declaran_consenso_ni_con_100(monkeypatch):
    """Politica de la v1: solo verifica lo construido desde la especificacion.

    Los casos que deriva un modelo fallan en las dos direcciones --- aprobaron
    codigo roto el 2026-09-24 y bloquearon codigo correcto el 25 --- asi que ni
    un 100% sobre ellos es una verificacion.
    """
    from engine.verificador import Veredicto
    v = Veredicto(8, 8, linea_base=4)
    v.via = "derivados"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert c.score == 100
    assert not c.passed and c.verificado_por_ejecucion is False


def test_el_arbitro_no_aprueba_con_un_caso_de_especificacion_fallado(monkeypatch):
    """Mismo fallo por el concilio: 15/16 -> 88 sobre la base no puede cerrar."""
    from engine.verificador import Veredicto
    v = Veredicto(15, 16, linea_base=8)
    v.via = "especificacion"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    c = a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    assert not c.passed, "un requisito incumplido no puede declarar consenso"
    assert c.score == 84, f"la cifra queda justo por debajo del umbral: {c.score}"


def test_el_arbitro_deja_constancia_de_cada_verificacion_de_especificacion(monkeypatch):
    """El orquestador necesita cada medicion para quedarse con la mejor."""
    from engine.verificador import Veredicto
    v = Veredicto(15, 16, linea_base=8, detalle=[
        {"entrada": "validar_token_telegram('!x')", "obtenido": "True",
         "esperado": "False", "correcto": False}])
    v.via = "especificacion"
    a, mem, bb = _arbitro_con_veredicto(monkeypatch, v)
    a.evaluate_solution(mem, threshold=85, espera_codigo=True)
    uv = bb.shared_notes.get("ultimo_veredicto")
    assert uv and uv["aciertos"] == 15 and uv["total"] == 16
    assert uv["fallos"] == ["validar_token_telegram('!x')"]
    assert "def validar_token_telegram" in uv["codigo"]
