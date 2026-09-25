"""Pruebas de la via «el modelo extrae, Python construye».

Todo aqui es sin red: la unica parte con modelo es `extraer_formato`, y se
prueba sustituyendo la invocacion.
"""
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.especificacion import (  # noqa: E402
    casos_desde_formato,
    expandir_alfabeto,
    extraer_formato,
    generar_valores,
    parsear_formato,
)
from engine.verificador import ejecutar_verificacion  # noqa: E402

ENUNCIADO = (
    "Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool "
    "que devuelva True solo si el token tiene el formato valido de la API de "
    "Telegram: identificador numerico, DOS PUNTOS, y un secreto de EXACTAMENTE "
    "35 caracteres del alfabeto [A-Za-z0-9_-]."
)
SPEC_TOKEN = {"aplica": True, "funcion": "validar_token_telegram", "partes": [
    {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 1, "longitud_max": 0},
    {"tipo": "separador", "texto": ":"},
    {"tipo": "campo", "alfabeto": "A-Za-z0-9_-", "longitud_min": 35, "longitud_max": 35},
]}

CORRECTO = '''
import re
def validar_token_telegram(token):
    return bool(re.fullmatch(r"\\d+:[A-Za-z0-9_-]{35}", token or ""))
'''
# Verbatim del log del 2026-09-24: cuatro fallos independientes.
ROTO_REAL = '''
def validar_token_telegram(token):
    if len(token) != 43:
        return False
    if '.' not in token:
        return False
    if not token[:21].isdigit():
        return False
    if len(token[22:]) != 35 or not all(c in 'A-Za-z0-9_' for c in token[22:]):
        return False
    return True
'''
# Los que fallaron las noches anteriores: se equivocan por uno.
POR_UNO = '''
import re
def validar_token_telegram(token):
    return bool(re.fullmatch(r"\\d+:[A-Za-z0-9_-]{34,36}", token or ""))
'''


def _fmt():
    fmt, err = parsear_formato(SPEC_TOKEN, ENUNCIADO)
    assert fmt, err
    return fmt


# ─── alfabetos ───────────────────────────────────────────────────────────────

def test_expande_rangos_y_literales():
    a = expandir_alfabeto("A-Za-z0-9_-")
    assert len(a) == 26 + 26 + 10 + 2
    assert "_" in a and "-" in a and "!" not in a


def test_acepta_la_clase_con_corchetes():
    assert expandir_alfabeto("[0-9]") == "0123456789"


# ─── el nucleo: Python cuenta ────────────────────────────────────────────────

def test_todos_los_validos_tienen_exactamente_35():
    """LO QUE NINGUNO DE LOS CINCO MODELOS LOGRO."""
    for v, ok in generar_valores(_fmt()):
        if ok:
            assert len(v.split(":", 1)[1]) == 35, v


def test_esta_balanceado():
    vals = generar_valores(_fmt())
    pos = sum(ok for _, ok in vals)
    assert pos == len(vals) - pos, f"{pos} validos de {len(vals)}"
    assert len(vals) >= 8


def test_incluye_las_fronteras_de_longitud():
    """34 y 36 son donde el codigo de estas noches se equivocaba."""
    longitudes = {len(v.split(":", 1)[1]) for v, ok in generar_valores(_fmt())
                  if not ok and ":" in v}
    assert {34, 36} <= longitudes, longitudes


def test_la_regex_arbitra_cada_caso():
    """Autocomprobacion: ningun caso contradice la especificacion."""
    fmt = _fmt()
    for v, ok in generar_valores(fmt):
        assert fmt.cumple(v) == ok, f"{v!r} marcado {ok}"


def test_separa_correcto_de_roto_y_de_constante():
    """LA PRUEBA QUE IMPORTA: el conjunto distingue competencia de casualidad."""
    casos = casos_desde_formato(_fmt())
    bueno = ejecutar_verificacion(CORRECTO, casos)
    roto = ejecutar_verificacion(ROTO_REAL, casos)
    const = ejecutar_verificacion("def validar_token_telegram(t):\n    return False",
                                  casos)
    assert bueno.discrimina and bueno.puntuacion_util == 100
    assert roto.puntuacion_util == 0, "el codigo roto de esta noche tiene que caer"
    assert const.puntuacion_util == 0


def test_caza_el_error_por_uno():
    """El fallo recurrente: aceptar 34 o 36. Tiene que suspender."""
    v = ejecutar_verificacion(POR_UNO, casos_desde_formato(_fmt()))
    assert v.discrimina
    assert v.puntuacion_util < 85, f"el codigo por-uno saco {v.puntuacion_util}"


# ─── generalidad: no es solo para tokens de Telegram ─────────────────────────

def test_sirve_para_otro_formato():
    enunciado = ("Escribe es_matricula(s) que acepte tres letras mayusculas, un "
                 "guion y 4 digitos.")
    spec = {"aplica": True, "funcion": "es_matricula", "partes": [
        {"tipo": "campo", "alfabeto": "A-Z", "longitud_min": 3, "longitud_max": 3},
        {"tipo": "separador", "texto": "-"},
        {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 4, "longitud_max": 4},
    ]}
    # «tres» va en LETRA a proposito: en espanol es lo normal, y la primera
    # version de la defensa numerica lo rechazaba por no ver el digito.
    fmt, err = parsear_formato(spec, enunciado)
    assert fmt, err
    correcto = ("import re\ndef es_matricula(s):\n"
                "    return bool(re.fullmatch(r'[A-Z]{3}-[0-9]{4}', s))")
    v = ejecutar_verificacion(correcto, casos_desde_formato(fmt))
    assert v.discrimina and v.puntuacion_util == 100


# ─── defensas contra una extraccion equivocada ───────────────────────────────

def test_rechaza_un_numero_que_el_enunciado_no_dice():
    """Si el extractor dice 34 y el texto dice 35, invento."""
    spec = json.loads(json.dumps(SPEC_TOKEN))
    spec["partes"][2]["longitud_min"] = spec["partes"][2]["longitud_max"] = 34
    fmt, err = parsear_formato(spec, ENUNCIADO)
    assert fmt is None and "34" in err


def test_rechaza_una_funcion_que_el_enunciado_no_nombra():
    spec = {**SPEC_TOKEN, "funcion": "validar_token"}
    fmt, err = parsear_formato(spec, ENUNCIADO)
    assert fmt is None and "no aparece" in err


def test_aplica_false_no_es_un_formato():
    fmt, err = parsear_formato({"aplica": False, "funcion": "x", "partes": []}, ENUNCIADO)
    assert fmt is None


def test_max_menor_que_min_se_rechaza():
    spec = json.loads(json.dumps(SPEC_TOKEN))
    spec["partes"][2]["longitud_min"], spec["partes"][2]["longitud_max"] = 35, 1
    assert parsear_formato(spec, ENUNCIADO)[0] is None


def test_un_extractor_caido_no_revienta():
    def caido(prompt, esquema):
        raise TimeoutError("se agoto")
    fmt, err = extraer_formato(ENUNCIADO, caido)
    assert fmt is None and "TimeoutError" in err


def test_el_extractor_recibe_el_esquema():
    """Decodificacion restringida: la salida no puede salirse del esquema."""
    visto = {}

    def espia(prompt, esquema):
        visto["esquema"] = esquema
        visto["prompt"] = prompt
        return json.dumps(SPEC_TOKEN)
    fmt, _ = extraer_formato(ENUNCIADO, espia)
    assert fmt is not None
    assert visto["esquema"]["properties"]["partes"]["type"] == "array"
    # El enunciado va cercado como DATOS, no como instrucciones.
    assert "<<<ENUNCIADO" in visto["prompt"] and "ENUNCIADO>>>" in visto["prompt"]


def test_un_numero_en_letra_cuenta_como_dicho():
    """«tres letras» dice 3 aunque no haya un digito."""
    from engine.especificacion import aparece_cantidad
    assert aparece_cantidad(3, "tres letras mayusculas")
    assert aparece_cantidad(35, "EXACTAMENTE 35 caracteres")
    assert aparece_cantidad(4, "cuatro digitos")
    assert not aparece_cantidad(34, "EXACTAMENTE 35 caracteres")
    assert not aparece_cantidad(5, "veinticinco")      # no por subcadena


# ─── las defensas de la segunda ronda, cada una por un fallo MEDIDO ──────────

def test_un_separador_equivocado_se_corrige_desde_el_texto():
    """llama3.2 extrajo «.» y qwen «::» de un enunciado que dice «DOS PUNTOS».

    Con UN separador nombrado y UN separador en el formato, gana el texto.
    """
    for malo in (".", "::"):
        spec = json.loads(json.dumps(SPEC_TOKEN))
        spec["partes"][1]["texto"] = malo
        fmt, err = parsear_formato(spec, ENUNCIADO)
        assert fmt is not None, err
        assert fmt.separadores[0].texto == ":", f"{malo!r} no se corrigio"


def test_con_varios_separadores_nombrados_no_se_adivina():
    """Si el texto nombra dos, no hay forma segura de saber cual va: rechazo."""
    enunciado = ENUNCIADO + " Opcionalmente puede llevar un guion."
    spec = json.loads(json.dumps(SPEC_TOKEN))
    spec["partes"][1]["texto"] = "."
    fmt, err = parsear_formato(spec, enunciado)
    assert fmt is None and "nombra" in err


def test_el_separador_corregido_sigue_separando():
    """La correccion no puede romper la vara: el roto sigue cayendo."""
    spec = json.loads(json.dumps(SPEC_TOKEN))
    spec["partes"][1]["texto"] = "::"
    fmt, _ = parsear_formato(spec, ENUNCIADO)
    cs = casos_desde_formato(fmt)
    assert ejecutar_verificacion(CORRECTO, cs).puntuacion_util == 100
    assert ejecutar_verificacion(ROTO_REAL, cs).puntuacion_util == 0


def test_guion_bajo_no_se_confunde_con_guion():
    from engine.especificacion import separadores_nombrados
    assert separadores_nombrados("separados por guion bajo") == {"_"}
    assert separadores_nombrados("separados por un guion") == {"-"}


def test_acepta_la_firma_entera_como_nombre():
    """mistral y qwen devolvieron la firma con el nombre bien identificado."""
    spec = {**SPEC_TOKEN,
            "funcion": "def validar_token_telegram(token: str) -> bool:"}
    fmt, err = parsear_formato(spec, ENUNCIADO)
    assert fmt is not None, err
    assert fmt.funcion == "validar_token_telegram"


def test_traduce_un_alfabeto_escrito_como_regex():
    """llama3.2:3b devolvio «\\d+» y se expandia a «\\», «d», «+»."""
    assert expandir_alfabeto(r"\d+") == "0123456789"
    assert expandir_alfabeto("[A-Z]{3}") == "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def test_una_funcion_que_no_devuelve_bool_no_es_un_formato():
    """nemotron-mini extrajo un «formato» para a_segundos(...) -> int."""
    enunciado = ("Escribe una funcion Python llamada a_segundos(texto: str) -> int "
                 "que convierta duraciones como '2h' o '30m' a segundos.")
    spec = {"aplica": True, "funcion": "a_segundos", "partes": [
        {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 1, "longitud_max": 2}]}
    fmt, err = parsear_formato(spec, enunciado)
    assert fmt is None and "no es un validador" in err


# ─── integracion con verificar() ─────────────────────────────────────────────

def _derivador_que_no_se_debe_usar(prompt):
    raise AssertionError("se derivaron casos habiendo especificacion valida")


def test_verificar_usa_la_especificacion_cuando_aplica():
    from engine.verificador import verificar
    v, casos = verificar(ENUNCIADO, ROTO_REAL, _derivador_que_no_se_debe_usar,
                         invocar_json=lambda p, e: json.dumps(SPEC_TOKEN))
    assert v.via == "especificacion"
    assert v.discrimina and v.puntuacion_util == 0, "el codigo roto tiene que caer"


def test_verificar_aprueba_el_correcto_por_la_via_nueva():
    from engine.verificador import verificar
    v, _ = verificar(ENUNCIADO, CORRECTO, _derivador_que_no_se_debe_usar,
                     invocar_json=lambda p, e: json.dumps(SPEC_TOKEN))
    assert v.via == "especificacion" and v.puntuacion_util == 100


def test_si_no_aplica_cae_a_derivar():
    """Para tareas que no son de formato, la via antigua sigue viva."""
    from engine.verificador import verificar
    llamado = {}

    def derivador(prompt):
        llamado["si"] = True
        return '[{"entrada": "validar_token_telegram(\\"x\\")", "esperado": "False"}]'
    v, _ = verificar(ENUNCIADO, CORRECTO, derivador,
                     invocar_json=lambda p, e: json.dumps(
                         {"aplica": False, "funcion": "", "partes": []}))
    assert llamado.get("si"), "no cayo a la derivacion"
    assert v.via == "derivados"


def test_si_el_extractor_revienta_cae_a_derivar():
    from engine.verificador import verificar

    def caido(p, e):
        raise TimeoutError("se agoto")
    v, _ = verificar(ENUNCIADO, CORRECTO,
                     lambda p: '[{"entrada": "validar_token_telegram(\\"x\\")", '
                               '"esperado": "False"}]',
                     invocar_json=caido)
    assert v.via == "derivados"


def test_sin_extractor_el_comportamiento_es_el_de_antes():
    from engine.verificador import verificar
    v, _ = verificar(ENUNCIADO, CORRECTO,
                     lambda p: '[{"entrada": "validar_token_telegram(\\"x\\")", '
                               '"esperado": "False"}]')
    assert v.via == "derivados"


# ─── Defensa de cantidades: el fallo en vivo del 2026-09-25 ─────────────────
# Por Telegram, con otra redacción («que acepte…»), el extractor dio al
# identificador longitud máxima 1; «un secreto» contaba como el 1 y el caso
# '18:<35 válidos>' → False rechazó 4 rondas seguidas un código correcto.

ENUNCIADO_VIVO = (
    "Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool "
    "que acepte identificador numerico, DOS PUNTOS y un secreto de EXACTAMENTE 35 "
    "caracteres del alfabeto [A-Za-z0-9_-]"
)


def _spec_token(id_min, id_max):
    return {"aplica": True, "funcion": "validar_token_telegram", "partes": [
        {"tipo": "campo", "alfabeto": "0-9", "longitud_min": id_min, "longitud_max": id_max},
        {"tipo": "separador", "texto": ":"},
        {"tipo": "campo", "alfabeto": "A-Za-z0-9_-", "longitud_min": 35, "longitud_max": 35},
    ]}


def test_el_articulo_un_no_justifica_un_tope_de_1():
    fmt, motivo = parsear_formato(_spec_token(1, 1), ENUNCIADO_VIVO)
    assert fmt is None and "cantidad 1" in motivo


def test_dos_puntos_no_justifica_la_cantidad_2():
    fmt, motivo = parsear_formato(_spec_token(2, 2), ENUNCIADO_VIVO)
    assert fmt is None and "cantidad 2" in motivo


def test_un_numero_dicho_una_vez_no_mide_dos_campos():
    fmt, motivo = parsear_formato(_spec_token(35, 35), ENUNCIADO_VIVO)
    assert fmt is None and "35" in motivo and "2 campos" in motivo


def test_la_especificacion_correcta_del_enunciado_vivo_pasa():
    fmt, motivo = parsear_formato(_spec_token(1, 0), ENUNCIADO_VIVO)
    assert fmt is not None, motivo
    casos = casos_desde_formato(fmt)
    v = ejecutar_verificacion(CORRECTO, casos)
    assert v.aciertos == v.total == len(casos)


def test_un_solo_y_la_cifra_si_justifican_el_1():
    from engine.especificacion import aparece_cantidad
    assert aparece_cantidad(1, "un solo digito")
    assert aparece_cantidad(1, "longitud 1")
    assert not aparece_cantidad(1, "un secreto y una clave")
    assert not aparece_cantidad(2, "separados por dos puntos")
    assert aparece_cantidad(2, "dos letras y dos puntos")


def test_la_misma_cantidad_dicha_dos_veces_mide_dos_campos():
    enunciado = ("Escribe una funcion Python llamada es_codigo(s: str) -> bool que "
                 "acepte 4 digitos, un guion y 4 letras")
    fmt, motivo = parsear_formato({"aplica": True, "funcion": "es_codigo", "partes": [
        {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 4, "longitud_max": 4},
        {"tipo": "separador", "texto": "-"},
        {"tipo": "campo", "alfabeto": "A-Za-z", "longitud_min": 4, "longitud_max": 4},
    ]}, enunciado)
    assert fmt is not None, motivo


def test_el_extractor_reintenta_una_vez_con_el_motivo():
    prompts = []
    respuestas = [json.dumps(_spec_token(1, 1)), json.dumps(_spec_token(1, 0))]

    def invocar(prompt, esquema):
        prompts.append(prompt)
        return respuestas[len(prompts) - 1]
    fmt, motivo = extraer_formato(ENUNCIADO_VIVO, invocar)
    assert fmt is not None, motivo
    assert len(prompts) == 2 and "cantidad 1" in prompts[1]


def test_el_reintento_pasa_por_las_mismas_defensas():
    llamadas = []

    def invocar(prompt, esquema):
        llamadas.append(prompt)
        return json.dumps(_spec_token(1, 1))
    fmt, motivo = extraer_formato(ENUNCIADO_VIVO, invocar)
    assert fmt is None and len(llamadas) == 2


def test_sin_formato_no_hay_reintento():
    llamadas = []

    def invocar(prompt, esquema):
        llamadas.append(prompt)
        return json.dumps({"aplica": False, "funcion": "", "partes": []})
    fmt, _ = extraer_formato("Escribe una funcion que ordene una lista", invocar)
    assert fmt is None and len(llamadas) == 1


def test_el_esquema_acota_las_cadenas_para_que_no_haya_bucles():
    # Sin topes, qwen se quedaba en bucle dentro de "funcion" hasta los 180 s.
    from engine.especificacion import ESQUEMA_FORMATO
    props = ESQUEMA_FORMATO["properties"]
    partes = props["partes"]
    assert props["funcion"].get("maxLength")
    assert partes.get("maxItems")
    for campo in ("texto", "alfabeto"):
        assert partes["items"]["properties"][campo].get("maxLength")
