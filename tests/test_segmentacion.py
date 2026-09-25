"""Pruebas del segmentador: tarea / reglas / limites / rechazar.

Sin red: la invocacion al modelo se sustituye. Lo que se fija aqui es la
regla central --- el segmentador REESCRIBE, no calcula --- y que ante un
fallo devuelva vacio en vez de inventar.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.segmentacion import (  # noqa: E402
    bloque_para_coder,
    parsear_segmentos,
    segmentar,
)

SEGUNDOS = ("Escribe una funcion Python llamada a_segundos(texto: str) -> int que "
            "convierta duraciones como '2h', '30m', '45s', '1h30m' a segundos totales. "
            "Devuelve 0 si el texto no es una duracion valida.")


def test_descarta_un_valor_calculado():
    """«2h = 7200» es un calculo: medido, los modelos locales calculan mal
    (uno derivo '2h' -> 120). El enunciado no dice 7200, asi que no entra."""
    s = parsear_segmentos({"tarea": "t", "reglas": ["2h equivale a 7200 segundos",
                                                    "acepta horas con el sufijo h"],
                           "limites": [], "rechazar": []}, SEGUNDOS)
    assert s.reglas == ["acepta horas con el sufijo h"]
    assert s.descartadas and "7200" in s.descartadas[0][1]


def test_conserva_lo_que_el_enunciado_dice():
    s = parsear_segmentos({"tarea": "t", "reglas": ["acepta combinaciones como 1h30m"],
                           "limites": [], "rechazar": ["devuelve 0 si no es valida"]},
                          SEGUNDOS)
    assert s.reglas == ["acepta combinaciones como 1h30m"]
    assert s.rechazar == ["devuelve 0 si no es valida"]
    assert not s.descartadas


def test_un_numero_en_letra_del_enunciado_cuenta_como_dicho():
    e = "es_matricula(s) acepta tres letras mayusculas, un guion y cuatro digitos."
    s = parsear_segmentos({"tarea": "t", "reglas": [], "limites": ["3 letras y 4 digitos"],
                           "rechazar": []}, e)
    assert s.limites == ["3 letras y 4 digitos"], s.descartadas


def test_deduplica_y_acota():
    s = parsear_segmentos({"tarea": "t", "reglas": ["regla a", "Regla A", "", "  - regla b"],
                           "limites": [], "rechazar": []}, SEGUNDOS)
    assert s.reglas == ["regla a", "regla b"]


def test_ante_un_fallo_devuelve_vacio():
    def caido(p, e):
        raise TimeoutError("se agoto")
    assert segmentar(SEGUNDOS, caido).vacia
    assert segmentar(SEGUNDOS, lambda p, e: "no es json").vacia


def test_el_segmentador_recibe_el_esquema_y_el_enunciado_cercado():
    visto = {}

    def espia(p, e):
        visto.update(prompt=p, esquema=e)
        return json.dumps({"tarea": "t", "reglas": ["r"], "limites": [], "rechazar": []})
    segmentar(SEGUNDOS, espia)
    assert set(visto["esquema"]["required"]) == {"tarea", "reglas", "limites", "rechazar"}
    assert "<<<ENUNCIADO" in visto["prompt"] and SEGUNDOS in visto["prompt"]


def test_el_bloque_numera_todas_las_reglas():
    s = parsear_segmentos({"tarea": "convertir", "reglas": ["r1", "r2"],
                           "limites": ["l1"], "rechazar": ["x1"]}, SEGUNDOS)
    b = bloque_para_coder(s)
    for i, t in enumerate(("r1", "r2", "l1", "x1"), start=1):
        assert f"{i}. {t}" in b


def test_sin_reglas_no_hay_bloque():
    assert bloque_para_coder(parsear_segmentos({}, SEGUNDOS)) == ""
    assert bloque_para_coder(None) == ""


def test_descarta_un_numero_inventado_de_muchas_cifras():
    """codegemma se invento «rango de 0 a 999999999»; la defensa miraba solo
    numeros de hasta 6 cifras y lo dejo pasar."""
    s = parsear_segmentos({"tarea": "t", "reglas": [],
                           "limites": ["Los valores enteros deben estar en el rango de 0 a 999999999."],
                           "rechazar": []}, SEGUNDOS)
    assert s.limites == [] and s.descartadas


def test_no_parte_decimales_ni_direcciones():
    from engine.segmentacion import _numeros
    assert _numeros("version 3.14") == []
    assert _numeros("la ip 192.168.1.1 es valida") == []
    assert _numeros("de 1 a 3999, en mayusculas") == [1, 3999]
    assert _numeros("combinaciones como 1h30m") == []


# ─── cableado: las reglas tienen que LLEGAR al coder, en los dos caminos ─────

def _pizarra_con_reglas():
    from memory.blackboard import Blackboard
    bb = Blackboard(task_id="t", session_id="s", user_prompt=SEGUNDOS)
    bb.shared_notes["reglas_enunciado"] = "=== REGLAS ===\n  1. acepta el sufijo h"
    return bb


def test_las_reglas_llegan_al_construir():
    ctx = _pizarra_con_reglas().get_context_for_coder()
    assert "1. acepta el sufijo h" in ctx
    assert "'reglas_enunciado'" not in ctx, "no debe volcarse como diccionario crudo"


def test_las_reglas_llegan_al_refinar():
    bb = _pizarra_con_reglas()
    bb.update_code("```python\ndef a_segundos(t): return 0\n```")
    bb.add_critique("falla", score=0)
    assert "1. acepta el sufijo h" in bb.get_context_for_refinement()


def test_el_orquestador_segmenta_una_vez_y_guarda_el_bloque(monkeypatch):
    from types import SimpleNamespace as NS
    import engine.tool_agent as ta
    from engine.orchestrator import ConsensusOrchestrator
    from memory.blackboard import Blackboard
    llamadas, cargas = [], []
    monkeypatch.setattr(ta, "run_with_tools", lambda **k: (llamadas.append(k), json.dumps(
        {"tarea": "convertir", "reglas": ["acepta el sufijo h"], "limites": [],
         "rechazar": ["devuelve 0 si no es valida"]}))[1])
    orq = ConsensusOrchestrator.__new__(ConsensusOrchestrator)
    orq._segmentador, orq.sequential, orq.settle_seconds = "qwen2.5-coder:7b", True, 0
    orq.ollama_host = "http://x"
    orq.lifecycle = NS(ensure_exclusive=lambda m, settle_seconds=1.0, num_ctx=None:
                       cargas.append((m, num_ctx)))
    bb = Blackboard(task_id="t", session_id="s", user_prompt=SEGUNDOS)
    orq._segmentar_enunciado(bb)
    orq._segmentar_enunciado(bb)                  # la segunda no debe repetir
    assert len(llamadas) == 1, "segmento dos veces la misma tarea"
    assert cargas == [("qwen2.5-coder:7b", 4096)], "la precarga tiene que llevar ventana"
    assert llamadas[0]["temperature"] == 0.0
    assert "acepta el sufijo h" in bb.shared_notes["reglas_enunciado"]


def test_el_orquestador_real_lee_el_segmentador_de_la_configuracion():
    from engine.orchestrator import ConsensusOrchestrator
    raiz = Path(__file__).resolve().parents[1]
    orq = ConsensusOrchestrator(config_path=str(raiz / "config.yaml"))
    assert orq._segmentador == "qwen2.5-coder:7b"
