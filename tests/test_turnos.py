"""Tests del motor de turnos. No levantan Ollama: la invocación va inyectada."""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.turnos import (  # noqa: E402
    PASO,
    REFINO,
    MemoriaTurnos,
    MotorTurnos,
    Turno,
    componer_contexto,
    presupuesto_material,
)

PERFIL = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "profiles" / "niveles.yaml").read_text(
        encoding="utf-8"
    )
)


def _motor(respuestas, tmp_path, perfil=None):
    """Motor con un invocador que devuelve respuestas predefinidas."""
    secuencia = iter(respuestas)
    llamados = []

    def invocar(modelo, ctx, ventana):
        llamados.append((modelo, ctx, ventana))
        return next(secuencia)

    p = dict(perfil or PERFIL)
    p["memoria"] = {"store": str(tmp_path / "turnos.jsonl"), "turnos_visibles": 6}
    m = MotorTurnos(p, invocar=invocar)
    return m, llamados


# ─── presupuesto de contexto ─────────────────────────────────────────────────

def test_material_baja_con_el_numero_de_turno():
    """El turno hereda lo destilado, así que necesita menos material bruto.

    Si material y acumulado crecieran a la vez, el último turno se ahogaría.
    """
    esc = PERFIL["escalado_contexto"]
    t1 = presupuesto_material(esc, 131072, 1)
    t2 = presupuesto_material(esc, 131072, 2)
    t3 = presupuesto_material(esc, 131072, 3)
    assert t1 > t2 > t3


def test_ventana_chica_recibe_menos_material():
    esc = PERFIL["escalado_contexto"]
    assert presupuesto_material(esc, 4096, 1) < presupuesto_material(esc, 131072, 1)


def test_ventana_desconocida_no_revienta():
    esc = PERFIL["escalado_contexto"]
    assert presupuesto_material(esc, 16384, 1) > 0


# ─── composición del contexto ────────────────────────────────────────────────

def test_el_acumulado_sobrevive_aunque_el_material_no_quepa():
    """Regresión: recortar el acumulado convierte la deliberación en N
    intentos independientes, que es justo lo que los turnos evitan."""
    previo = Turno(n=1, modelo="m", rol="explorador", veredicto=REFINO,
                   puntuacion=60, borrador="HALLAZGO IMPORTANTE",
                   objeciones=["falta verificar la ruta"])
    ctx = componer_contexto("la tarea", [previo], "X" * 10_000,
                            max_material_chars=100)
    assert "HALLAZGO IMPORTANTE" in ctx
    assert "falta verificar la ruta" in ctx
    assert "recortado" in ctx


def test_sin_previos_no_inventa_seccion_de_turnos():
    ctx = componer_contexto("la tarea", [], "material", 1000)
    assert "TURNOS ANTERIORES" not in ctx


# ─── el bucle ────────────────────────────────────────────────────────────────

def test_el_segundo_turno_ve_el_borrador_del_primero(tmp_path):
    m, llamados = _motor(
        [(REFINO, 50, "borrador del primero", ["objeción A"]),
         (PASO, 95, "borrador del segundo", [])],
        tmp_path,
    )
    m.correr_nivel("t1", "enunciado", "investigacion", "ligero")
    _, ctx_segundo, _ = llamados[1]
    assert "borrador del primero" in ctx_segundo
    assert "objeción A" in ctx_segundo


def test_media_decide_si_alcanza_el_umbral(tmp_path):
    m, _ = _motor([(PASO, 90, "a", []), (PASO, 92, "b", [])], tmp_path)
    r = m.correr_nivel("t2", "e", "investigacion", "ligero")
    assert r.media == 91.0
    assert r.alcanzo_umbral

    m2, _ = _motor([(REFINO, 40, "a", []), (REFINO, 50, "b", [])], tmp_path)
    r2 = m2.correr_nivel("t3", "e", "investigacion", "ligero")
    assert not r2.alcanzo_umbral


def test_un_modelo_caido_no_aborta_el_nivel(tmp_path):
    """El siguiente turno debe poder seguir desde lo que haya."""
    def invocar(modelo, ctx, ventana):
        if "gemma" in modelo:
            raise RuntimeError("ollama no responde")
        return (REFINO, 55, "lo que alcancé a escribir", [])

    p = dict(PERFIL)
    p["memoria"] = {"store": str(tmp_path / "t.jsonl"), "turnos_visibles": 6}
    r = MotorTurnos(p, invocar=invocar).correr_nivel(
        "t4", "e", "investigacion", "ligero")
    assert len(r.turnos) == 2
    caido = r.turnos[-1]
    assert caido.veredicto == REFINO
    assert caido.puntuacion == 0
    assert any("no respondió" in o for o in caido.objeciones)


def test_veredicto_invalido_se_trata_como_refino(tmp_path):
    """Ante la duda, otra vuelta: dar por bueno lo no revisado es peor."""
    m, _ = _motor([("QUIZÁS", 99, "a", []), (PASO, 99, "b", [])], tmp_path)
    r = m.correr_nivel("t5", "e", "investigacion", "ligero")
    assert r.turnos[0].veredicto == REFINO


def test_puntuacion_fuera_de_rango_se_acota(tmp_path):
    m, _ = _motor([(PASO, 9999, "a", []), (PASO, -5, "b", [])], tmp_path)
    r = m.correr_nivel("t6", "e", "investigacion", "ligero")
    assert r.turnos[0].puntuacion == 100
    assert r.turnos[1].puntuacion == 0


# ─── escalado entre niveles ──────────────────────────────────────────────────

def test_escala_de_nivel_cuando_no_alcanza(tmp_path):
    usados = []

    def invocar(modelo, ctx, ventana):
        usados.append(modelo)
        # ligero (2 turnos) flojo; intermedio (3 turnos) alcanza
        return (REFINO, 40, "flojo", []) if len(usados) <= 2 else (PASO, 95, "bueno", [])

    p = dict(PERFIL)
    p["memoria"] = {"store": str(tmp_path / "t.jsonl"), "turnos_visibles": 6}
    r = MotorTurnos(p, invocar=invocar).deliberar(
        "t7", "e", "investigacion", nivel_inicial="ligero")
    assert r.nivel == "intermedio"
    assert r.alcanzo_umbral
    assert len(usados) == 5   # 2 del ligero + 3 del intermedio


def test_no_escala_si_el_primer_nivel_basta(tmp_path):
    m, llamados = _motor([(PASO, 95, "a", []), (PASO, 96, "b", [])], tmp_path)
    r = m.deliberar("t8", "e", "investigacion", nivel_inicial="ligero")
    assert r.nivel == "ligero"
    assert len(llamados) == 2


def test_el_nivel_siguiente_hereda_el_trabajo(tmp_path):
    ctxs = []

    def invocar(modelo, ctx, ventana):
        ctxs.append(ctx)
        return (REFINO, 40, "LO QUE DEJO EL LIGERO", []) if len(ctxs) <= 2 \
            else (PASO, 95, "ok", [])

    p = dict(PERFIL)
    p["memoria"] = {"store": str(tmp_path / "t.jsonl"), "turnos_visibles": 6}
    MotorTurnos(p, invocar=invocar).deliberar(
        "t9", "e", "investigacion", nivel_inicial="ligero")
    assert "LO QUE DEJO EL LIGERO" in ctxs[2]


# ─── detección de anclaje ────────────────────────────────────────────────────

def test_detecta_que_los_turnos_solo_asintieron(tmp_path):
    """Si nadie objeta tras el primero, el nivel se ancló: no deliberó."""
    m, _ = _motor([(PASO, 90, "a", []), (PASO, 91, "b", [])], tmp_path)
    r = m.correr_nivel("t10", "e", "investigacion", "ligero")
    assert not r.cambio_de_opinion

    m2, _ = _motor([(PASO, 90, "a", []), (REFINO, 92, "b", ["objeto"])], tmp_path)
    r2 = m2.correr_nivel("t11", "e", "investigacion", "ligero")
    assert r2.cambio_de_opinion


# ─── memoria ─────────────────────────────────────────────────────────────────

def test_la_memoria_guarda_el_borrador_no_solo_el_marcador(tmp_path):
    """Regresión: la memoria anterior guardaba quién corrió y qué nota sacó.
    Con eso el siguiente modelo no tiene nada que refinar."""
    mem = MemoriaTurnos(str(tmp_path / "m.jsonl"))
    mem.anotar("tarea-x", Turno(n=1, modelo="m", rol="r", veredicto=PASO,
                                puntuacion=88, borrador="EL CONTENIDO REAL",
                                objeciones=["una objeción"]))
    filas = mem.leer("tarea-x")
    assert len(filas) == 1
    assert filas[0]["borrador"] == "EL CONTENIDO REAL"
    assert filas[0]["objeciones"] == ["una objeción"]


def test_la_memoria_separa_por_tarea(tmp_path):
    mem = MemoriaTurnos(str(tmp_path / "m.jsonl"))
    mem.anotar("A", Turno(n=1, modelo="m", rol="r", veredicto=PASO,
                          puntuacion=1, borrador="de A"))
    mem.anotar("B", Turno(n=1, modelo="m", rol="r", veredicto=PASO,
                          puntuacion=2, borrador="de B"))
    assert [f["borrador"] for f in mem.leer("A")] == ["de A"]


def test_la_memoria_corrupta_no_revienta(tmp_path):
    ruta = tmp_path / "m.jsonl"
    mem = MemoriaTurnos(str(ruta))
    mem.anotar("A", Turno(n=1, modelo="m", rol="r", veredicto=PASO,
                          puntuacion=1, borrador="buena"))
    with ruta.open("a", encoding="utf-8") as f:
        f.write("{esto no es json\n")
    assert len(mem.leer("A")) == 1


# ─── enrutado de auditorías ───────────────────────────────────────────────────
# Regresión: "audita" vivía solo en optimize_keywords y exigía código en el
# prompt. Auditar un proyecto entero nunca lo cumple, así que caía al default
# FULL_CONSENSUS_CODING. Medido: 70 de 105 min en el coder, y la síntesis
# entregó un ConfigurationManager inventado en vez de hallazgos.

def test_auditar_un_proyecto_no_es_programar():
    from engine.router import PipelineType, TaskRouter
    prompt = ("AUDITORÍA DEL PROYECTO SENTINEL OMEGA / CONCILIO. Revisa el "
              "contexto inyectado y produce hallazgos priorizados con "
              "severidad, archivo y acción sugerida.")
    assert TaskRouter.route_task(prompt) == PipelineType.RESEARCH_AND_ANALYSIS


def test_auditar_un_fragmento_de_codigo_si_es_optimizacion():
    from engine.router import PipelineType, TaskRouter
    prompt = "audita este código:\n```python\ndef f(): pass\n```"
    assert TaskRouter.route_task(prompt) == PipelineType.CODE_OPTIMIZATION


def test_audit_project_no_deja_adivinar_al_router(monkeypatch):
    """Quien llama conoce el tipo: no debe depender de palabras clave.

    Se EJECUTA la ruta, no se inspecciona el texto: la primera versión de
    este test solo miraba que la cadena estuviera en el código fuente y pasó
    en verde mientras audit_project reventaba con NameError al correrla.
    """
    from engine.orchestrator import ConsensusOrchestrator
    from engine.router import PipelineType

    visto = {}

    def falso_run(self, user_prompt, shared_memory=None, on_stage_start=None,
                  on_token=None, on_stage_end=None, pipeline_type=None):
        visto["tipo"] = pipeline_type
        return "blackboard"

    monkeypatch.setattr(ConsensusOrchestrator, "run_consensus", falso_run)
    orq = ConsensusOrchestrator.__new__(ConsensusOrchestrator)
    orq.db_path = ":memory:"
    orq.inject_sentinel = False
    assert ConsensusOrchestrator.audit_project(orq, focus="tests") == "blackboard"
    assert visto["tipo"] == PipelineType.RESEARCH_AND_ANALYSIS


def test_run_consensus_acepta_el_tipo_forzado():
    import inspect

    from engine.orchestrator import ConsensusOrchestrator
    firma = inspect.signature(ConsensusOrchestrator.run_consensus)
    assert "pipeline_type" in firma.parameters
    assert firma.parameters["pipeline_type"].default is None


# ─── nombres indefinidos ──────────────────────────────────────────────────────

def test_ningun_nombre_indefinido_en_el_motor():
    """Guarda contra el NameError que ningún test unitario caza.

    Al forzar `pipeline_type` se coló un `logger.info(...)` en un módulo que
    no usa logging. Los 21 tests pasaron en verde y la auditoría reventó al
    lanzarla: el test de audit_project sustituye run_consensus entero, así que
    su cuerpo real nunca se ejecutaba. Un nombre indefinido es trabajo de
    análisis estático, no de pruebas.
    """
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    objetivos = ["engine", "memory", "telegram_bot.py", "cli.py"]
    r = subprocess.run(
        [sys.executable, "-m", "pyflakes", *objetivos],
        cwd=raiz, capture_output=True, text=True,
    )
    indefinidos = [l for l in r.stdout.splitlines() if "undefined name" in l]
    assert not indefinidos, "nombres indefinidos:\n" + "\n".join(indefinidos)
