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
