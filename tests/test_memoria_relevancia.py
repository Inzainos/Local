"""Pruebas del filtro de relevancia de la memoria historica.

EL FALLO QUE LAS ORIGINA
------------------------
El 2026-09-24, en una tarea de validacion de tokens de Telegram, el Concilio
entrego `validar_token_telegram` Y ADEMAS `es_palindromo`. La causa no estaba
en el modelo: la memoria historica inyectaba las 5 tareas MAS RECIENTES, por
fecha y sin filtro alguno, y dos eran de otras baterias:

  [CONSENSO 88] ... validar_token_telegram ...
  [CONSENSO 88] ... es_palindromo ...        <- nada que ver
  [SIN CONSENSO 78] ... a_segundos ...       <- nada que ver

El modelo leyo ese enunciado en su contexto y lo resolvio tambien. Ruido
inyectado en una tarea cuyo problema medido es la precision.
"""
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from memory.shared_context import (  # noqa: E402
    RELEVANCIA_MINIMA,
    filtrar_por_relevancia,
    palabras_informativas,
    pesos_idf,
    relevancia,
)

# Los enunciados REALES de la corrida del 2026-09-24.
TOKEN = ("Escribe una funcion Python llamada validar_token_telegram(token: str) "
         "-> bool que devuelva True solo si el token tiene el formato valido de "
         "la API de Telegram: identificador numerico, DOS PUNTOS, y un secreto "
         "de EXACTAMENTE 35 caracteres del alfabeto [A-Za-z0-9_-].")
PALINDROMO = ("Escribe una funcion Python llamada es_palindromo(texto: str) -> "
              "bool que devuelva True si el texto es palindromo ignorando "
              "mayusculas, espacios y signos de puntuacion.")
SEGUNDOS = ("Escribe una funcion Python llamada a_segundos(texto: str) -> int "
            "que convierta duraciones como '2h', '30m', '45s' a segundos.")
AUDITORIA = ("AUDITORIA DEL PROYECTO SENTINEL OMEGA / CONCILIO. Revisa el "
             "codigo y dame hallazgos con severidad y ubicacion.")


def _tareas(*prompts):
    return [{"user_prompt": p, "task_id": f"t{i}", "consensus_score": 90,
             "consensus_reached": True} for i, p in enumerate(prompts)]


# ─── la fuga, exactamente como ocurrio ───────────────────────────────────────

def test_el_palindromo_no_entra_en_la_tarea_del_token():
    """EL FALLO DEL 2026-09-24."""
    sel = filtrar_por_relevancia(
        TOKEN, _tareas(TOKEN, PALINDROMO, SEGUNDOS, AUDITORIA), limite=5)
    textos = [t["user_prompt"] for t in sel]
    assert PALINDROMO not in textos, "es_palindromo volvio a colarse"
    assert SEGUNDOS not in textos
    assert TOKEN in textos, "el antecedente del MISMO tema si tiene que entrar"


def test_la_plantilla_compartida_no_crea_parecido():
    """Todos empiezan «Escribe una funcion Python llamada...».

    Un parecido por palabras crudas los declararia semejantes. Por eso cada
    palabra se pesa por lo informativa que es.
    """
    idf = pesos_idf([TOKEN, PALINDROMO, SEGUNDOS])
    r_mismo = relevancia(TOKEN, TOKEN, idf)
    r_otro = relevancia(TOKEN, PALINDROMO, idf)
    assert r_mismo == pytest.approx(1.0)
    assert r_otro < RELEVANCIA_MINIMA, (
        f"misma plantilla y otro tema dio {r_otro:.3f}, por encima del corte "
        f"{RELEVANCIA_MINIMA}")


def test_una_palabra_comun_pesa_menos_pero_no_cero():
    """Si aparece en todos distingue poco, pero anularla rompe el caso homogeneo.

    Mi primera version usaba log(n/f) y daba EXACTAMENTE 0 a las palabras
    presentes en todos los documentos. Con un corpus homogeneo --- solo tareas
    de token --- eso ponia todos los pesos a 0, la relevancia salia 0 y se
    descartaban los antecedentes BUENOS. Con idf suavizado, comun pesa 1 y
    distintiva pesa mas: se conserva el orden sin anular nada.
    """
    idf = pesos_idf(["gatos marrones corren", "gatos azules saltan",
                     "gatos verdes duermen"])
    assert idf["gatos"] > 0, "anular la palabra comun rompe el corpus homogeneo"
    assert idf["marrones"] > idf["gatos"], "la distintiva tiene que pesar mas"


def test_corpus_homogeneo_no_descarta_los_buenos():
    """EL CASO DEGENERADO: si todo lo previo es del mismo tema, sigue valiendo."""
    sel = filtrar_por_relevancia(TOKEN, _tareas(TOKEN, TOKEN, TOKEN), limite=3)
    assert len(sel) == 3, ("con antecedentes identicos y del mismo tema, "
                           "descartarlos todos es el error contrario")
    assert sel[0]["relevancia"] == pytest.approx(1.0)


# ─── lo que NO se debe hacer cuando no hay nada relevante ────────────────────

def test_sin_antecedente_relevante_no_se_inyecta_nada():
    """«No hay nada parecido» no es «aqui van los ultimos».

    Inyectar los mas recientes por no tener mejores ES el fallo corregido.
    """
    sel = filtrar_por_relevancia(
        "Escribe una funcion que calcule la transformada de Fourier de una senal",
        _tareas(PALINDROMO, SEGUNDOS, AUDITORIA), limite=5)
    assert sel == [], f"inyecto {len(sel)} antecedentes sin relacion"


def test_consulta_vacia_no_recupera_nada():
    assert filtrar_por_relevancia("", _tareas(TOKEN, PALINDROMO), limite=5) == []


def test_sin_candidatos_no_revienta():
    assert filtrar_por_relevancia(TOKEN, [], limite=5) == []


# ─── orden, tope y trazabilidad ──────────────────────────────────────────────

def test_ordena_de_mas_a_menos_relevante():
    sel = filtrar_por_relevancia(
        TOKEN, _tareas(PALINDROMO, TOKEN, AUDITORIA), limite=5, minimo=0.0)
    rels = [t["relevancia"] for t in sel]
    assert rels == sorted(rels, reverse=True)
    assert sel[0]["user_prompt"] == TOKEN


def test_respeta_el_tope():
    sel = filtrar_por_relevancia(TOKEN, _tareas(*[TOKEN] * 9), limite=3)
    assert len(sel) == 3


def test_anota_la_relevancia_para_poder_auditarla():
    sel = filtrar_por_relevancia(TOKEN, _tareas(TOKEN), limite=5)
    assert "relevancia" in sel[0], ("sin la cifra no hay forma de saber por que "
                                    "un antecedente entro")


# ─── separacion entre familias de tarea ──────────────────────────────────────

def test_una_auditoria_no_arrastra_tareas_de_codigo():
    sel = filtrar_por_relevancia(
        AUDITORIA, _tareas(TOKEN, PALINDROMO, SEGUNDOS, AUDITORIA), limite=5)
    assert [t["user_prompt"] for t in sel] == [AUDITORIA]


def test_las_palabras_cortas_no_cuentan():
    """«una», «que», «de» no cargan tema."""
    p = palabras_informativas("una funcion que valide de verdad el token")
    assert "una" not in p and "que" not in p
    assert "funcion" in p and "verdad" in p and "token" in p


# ─── integracion: el ORQUESTADOR tiene que usarlo ────────────────────────────
# El filtro puede estar perfecto y no estar conectado. Estos dos tests miran el
# bloque de memoria que se inyecta de verdad en los prompts.

class _MemoriaFalsa:
    def __init__(self, tareas):
        self._tareas = tareas

    def recuperar_tareas_previas(self, limit=5, excluir_task_id=None):
        return list(self._tareas[:limit])

    def buscar_hechos(self, consulta, limite=2):
        return []


def _bloque(enunciado, tareas):
    from engine.orchestrator import ConsensusOrchestrator
    from memory.blackboard import Blackboard
    bb = Blackboard(task_id="actual", session_id="s", user_prompt=enunciado)
    # Sin __init__: no hace falta Ollama ni config para este metodo.
    orq = ConsensusOrchestrator.__new__(ConsensusOrchestrator)
    return ConsensusOrchestrator._bloque_memoria_historica(
        orq, _MemoriaFalsa(tareas), bb)


def test_el_bloque_inyectado_no_lleva_tareas_ajenas():
    """EL FALLO DEL 2026-09-24, visto desde el prompt real."""
    bloque = _bloque(TOKEN, _tareas(TOKEN, PALINDROMO, SEGUNDOS))
    assert "validar_token_telegram" in bloque
    assert "es_palindromo" not in bloque, (
        "el enunciado del palindromo sigue llegando al prompt: es lo que hizo "
        "que el Concilio entregara esa funcion ademas de la pedida")
    assert "a_segundos" not in bloque


def test_sin_nada_relevante_no_hay_bloque_de_memoria():
    """Cadena vacia, no «las cinco ultimas»."""
    bloque = _bloque(
        "Escribe una funcion que calcule la transformada de Fourier de una senal",
        _tareas(PALINDROMO, SEGUNDOS, AUDITORIA))
    assert bloque == "", f"inyecto un bloque de {len(bloque)} chars sin relacion"


def test_el_bloque_declara_la_relevancia():
    """Auditable: por que entro cada antecedente."""
    assert "rel=" in _bloque(TOKEN, _tareas(TOKEN))


# ─── memoria envenenada ──────────────────────────────────────────────────────
# Los siete hechos de knowledge_facts del 2026-09-24 se aprobaron antes del
# arreglo del verificador, todos de codigo roto (acierto real 78%, 38%, 78%,
# 50%), y se servian como «lo unico que el Concilio dio por bueno». Uno de
# validar_token acabo inyectado en la tarea a_segundos.

class _MemoriaConHechos(_MemoriaFalsa):
    def __init__(self, tareas, hechos):
        super().__init__(tareas)
        self._hechos = hechos

    def buscar_hechos(self, consulta, limite=2):
        return list(self._hechos[:limite])


def test_un_hecho_de_otra_tarea_no_entra_en_el_bloque():
    """EL FALLO DEL 2026-09-25: un hecho de validar_token en a_segundos."""
    from engine.orchestrator import ConsensusOrchestrator
    from memory.blackboard import Blackboard
    bb = Blackboard(task_id="actual", session_id="s", user_prompt=SEGUNDOS)
    mem = _MemoriaConHechos(
        _tareas(SEGUNDOS),
        [{"key": TOKEN, "value": "sintesis rota del token",
          "source_agent": "Concilio score=88/85"}])
    orq = ConsensusOrchestrator.__new__(ConsensusOrchestrator)
    bloque = ConsensusOrchestrator._bloque_memoria_historica(orq, mem, bb)
    assert "a_segundos" in bloque, "el antecedente propio si debe entrar"
    assert "sintesis rota del token" not in bloque, (
        "un hecho de validar_token volvio a colarse en a_segundos")


def test_no_se_archiva_lo_que_el_verificador_bloqueo():
    """Score de LECTURA 96 >= 85, pero sin consenso: no es un hecho aprobado."""
    from memory.blackboard import Blackboard
    from memory.shared_context import SharedMemory

    class _Almacen:
        guardados = []

        def save_fact(self, **k):
            self.guardados.append(k)

    m = SharedMemory.__new__(SharedMemory)
    m.store = _Almacen()
    bb = Blackboard(task_id="t", session_id="s", user_prompt="x")
    bb.consensus_score, bb.consensus_threshold = 96, 85
    bb.consensus_reached = False
    bb.final_synthesis = "codigo que nadie ejecuto"
    assert m.recordar_consenso(bb) is False
    assert m.store.guardados == []


def test_si_se_archiva_un_consenso_real():
    from memory.blackboard import Blackboard
    from memory.shared_context import SharedMemory

    class _Almacen:
        guardados = []

        def save_fact(self, **k):
            self.guardados.append(k)

    m = SharedMemory.__new__(SharedMemory)
    m.store = _Almacen()
    bb = Blackboard(task_id="t", session_id="s", user_prompt="x")
    bb.consensus_score, bb.consensus_threshold = 100, 85
    bb.consensus_reached = True
    bb.final_synthesis = "codigo verificado"
    assert m.recordar_consenso(bb) is True
