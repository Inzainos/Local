"""Pruebas del perfil por niveles: que las cifras cuadren con la maquina.

POR QUE EXISTEN
---------------
La primera version de profiles/niveles.yaml se dimensiono con `free` de WSL,
que no ve la memoria de Ollama porque Ollama corre en el host Windows. De ahi
salieron dos clases de error que ningun test detectaba:

  1. Catorce turnos pedian `ctx: 131072`. Con esa ventana deepseek-r1:8b mide
     23,93 GiB (medido) en un host de 11,71: las catorce excedian la maquina.
  2. `techo_ram_gb` era el PESO del modelo, no su huella. La cache KV escala
     lineal con la ventana y para el 8b a 131k pesa CUATRO VECES el modelo.

Y un tercero, de consistencia interna: el perfil `maximo` pedia ctx 24576 y
`escalado_contexto.por_ventana` no tenia escalon para 24576, asi que ese turno
se habria quedado sin presupuesto de material definido --- y habria caido a un
default en silencio, que es el patron que perseguimos toda la semana.
"""
import sys
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

# ─── presupuesto MEDIDO el 2026-09-24, no estimado ───────────────────────────
HOST_GIB = 11.71          # Win32_ComputerSystem.TotalPhysicalMemory
TECHO_CON_SENTINEL = 7.3  # host - Windows(2,02) - WSL(1,95) - margen
TECHO_SIN_SENTINEL = 9.2  # deteniendo Sentinel se liberan los 1,95 de WSL
SOBRECARGA = 1.05

# gemma3 lleva sliding_window=1024 y la mayoria de sus capas atienden solo una
# ventana local, asi que la formula plena lo sobreestima. Medido el 2026-09-24:
# concilio-arbitro (FROM gemma3:4b) a ctx 16384 pesa 3,57 GiB, no los 5,5 que
# da la formula --- su cache real es el 13% de la calculada. El factor esta
# CALIBRADO CON UN SOLO PUNTO: sirve para 16384 y hay que volver a medir antes
# de asignarle una ventana mucho mayor.
FRACCION_CACHE = {"gemma3:4b": 0.13}

# peso GiB, capas, kv_heads, head_dim, ventana maxima --- de /api/show y /api/tags
MODELOS = {
    "llama3.2:3b":      (1.88, 28, 8, 128, 131072),
    "nemotron-mini":    (2.51, 32, 8, 128,   4096),
    "gemma3:4b":        (3.11, 34, 4, 256, 131072),
    "mistral:7b":       (4.07, 32, 8, 128,  32768),
    "qwen2.5-coder:7b": (4.36, 28, 4, 128,  32768),
    "deepseek-r1:8b":   (4.87, 36, 8, 128, 131072),
    "deepseek-r1:14b":  (8.37, 48, 8, 128, 131072),
}


def huella(modelo: str, ctx: int) -> float:
    """peso + cache KV, en GiB. cache = 2(K,V) x capas x kv_heads x hd x ctx x 2B."""
    peso, capas, kvh, hd, _ = MODELOS[modelo]
    cache = 2 * capas * kvh * hd * ctx * 2 / 2**30
    cache *= FRACCION_CACHE.get(modelo, 1.0)
    return (peso + cache) * SOBRECARGA


@pytest.fixture(scope="module")
def perfil():
    return yaml.safe_load((RAIZ / "profiles" / "niveles.yaml").read_text(encoding="utf-8"))


def _turnos(perfil, incluir_maximo=True):
    """(familia, nivel, modelo, ctx) de cada turno declarado."""
    for fam in ("investigacion", "codigo"):
        for niv, cfg in perfil[fam].items():
            for t in cfg["turnos"]:
                yield fam, niv, t["model"], t["ctx"]
    if incluir_maximo:
        for fam in ("investigacion", "codigo"):
            for t in perfil["maximo"][fam]["turnos"]:
                yield "maximo", fam, t["model"], t["ctx"]


# ─── el fallo 1: ventanas que no caben ───────────────────────────────────────

def test_ningun_turno_pide_la_ventana_completa(perfil):
    """`ctx` es la ventana ASIGNADA, nunca el maximo del modelo."""
    culpables = [(f, n, m) for f, n, m, c in _turnos(perfil) if c >= 131072]
    assert not culpables, (
        f"piden la ventana completa: {culpables}. Con 131072 deepseek-r1:8b "
        f"mide 23,93 GiB medidos y el host tiene {HOST_GIB}")


def test_cada_turno_cabe_en_su_presupuesto(perfil):
    """Los niveles normales conviven con Sentinel; `maximo` lo requiere parado."""
    excesos = []
    for fam, niv, modelo, ctx in _turnos(perfil):
        techo = TECHO_SIN_SENTINEL if fam == "maximo" else TECHO_CON_SENTINEL
        h = huella(modelo, ctx)
        if h > techo:
            excesos.append(f"{fam}/{niv} {modelo}@{ctx} = {h:.1f} GiB > {techo}")
    assert not excesos, "no caben:\n  " + "\n  ".join(excesos)


def test_el_14b_no_aparece(perfil):
    """deepseek-r1:14b no entra en esta maquina ni con Sentinel parado.

    Solo «cabe» a ctx 2048 (9,2 GiB de 11,71), y con esa ventana no le entra
    ni el pack de memoria. Si alguien lo vuelve a poner, este test lo dice.
    """
    for fam, niv, modelo, ctx in _turnos(perfil):
        assert "14b" not in modelo, (
            f"{fam}/{niv} monta {modelo}@{ctx} = {huella(modelo, ctx):.1f} GiB; "
            f"el techo sin Sentinel es {TECHO_SIN_SENTINEL}")


# ─── el fallo 2: techos que eran el peso ─────────────────────────────────────

def test_el_techo_es_la_huella_del_mayor_no_su_peso(perfil):
    """techo_ram_gb debe cubrir la huella real del turno mas gordo del nivel."""
    for fam in ("investigacion", "codigo"):
        for niv, cfg in perfil[fam].items():
            peor = max(huella(t["model"], t["ctx"]) for t in cfg["turnos"])
            declarado = cfg["techo_ram_gb"]
            assert declarado >= peor - 0.1, (
                f"{fam}/{niv}: declara {declarado} pero su turno mayor mide "
                f"{peor:.1f} GiB. Sintoma de haber anotado el PESO del modelo.")
            assert declarado <= peor + 1.0, (
                f"{fam}/{niv}: declara {declarado} y el mayor mide {peor:.1f}; "
                f"un techo inflado hace creer que no cabe algo que si cabe")


# ─── el fallo 3: consistencia interna ────────────────────────────────────────

def test_todo_ctx_tiene_presupuesto_de_material(perfil):
    """Sin escalon, el turno se queda sin presupuesto y cae a un default."""
    escalones = set(perfil["escalado_contexto"]["por_ventana"])
    usados = {c for *_, c in _turnos(perfil)}
    usados |= {perfil["juez"][k]["ctx"] for k in perfil["juez"]}
    faltan = usados - escalones
    assert not faltan, (
        f"ctx sin escalon en escalado_contexto.por_ventana: {sorted(faltan)}")


def test_el_material_deja_sitio_al_acumulado(perfil):
    """El acumulado es prioritario: el material nuevo no puede comerse la ventana."""
    reserva = perfil["escalado_contexto"]["reserva_para_generacion"]
    for ctx, material in perfil["escalado_contexto"]["por_ventana"].items():
        entrada = ctx * (1 - reserva)
        assert material < entrada / 2, (
            f"ctx {ctx}: {material} tokens de material sobre {entrada:.0f} de "
            f"entrada no deja la mitad para el acumulado de los turnos previos")


def test_el_modelo_de_huella_predice_lo_medido():
    """La formula se valida contra /api/ps, si no es aritmetica sin anclaje."""
    for modelo, ctx, medido in [("llama3.2:3b", 16384, 3.80),
                                ("deepseek-r1:8b", 16384, 7.28),
                                ("deepseek-r1:8b", 131072, 23.93),
                                ("gemma3:4b", 16384, 3.57)]:
        calc = huella(modelo, ctx)
        err = abs(calc - medido) / medido
        assert err < 0.05, (f"{modelo}@{ctx}: calculado {calc:.2f} contra "
                            f"{medido} medido, error {100*err:.1f}%")


# ─── nemotron-mini queda reservado al portero ─────────────────────────────────
# Decision del operador el 2026-09-24: nemotron-mini SOLO como portero, donde su
# velocidad rinde, y fuera de cualquier otra tarea mientras no lo probemos.
#
# Las cifras medidas lo respaldan en los tres ejes frente a llama3.2:3b:
#
#                   peso   huella@4096   ventana nativa
#   nemotron-mini   2,51      3,2 GiB          4.096
#   llama3.2:3b     1,88      2,4 GiB        131.072
#
# Lo que NO esta medido es si razona mejor para clasificar. Eso hay que probarlo.

def test_nemotron_solo_es_portero(perfil):
    assert perfil["portero"]["model"] == "nemotron-mini"
    assert perfil["capitan"]["model"] != "nemotron-mini", (
        "el capitan era nemotron-mini; llama3.2:3b es mas pequeno, ocupa 0,8 GiB "
        "menos y tiene 32 veces mas ventana")
    for fam, niv, modelo, _ in _turnos(perfil):
        assert "nemotron" not in modelo, f"{fam}/{niv} monta {modelo}"
    for k in perfil["juez"]:
        assert "nemotron" not in perfil["juez"][k]["model"]


def test_nemotron_no_es_respaldo_de_nadie():
    """Un respaldo silencioso a nemotron-mini es participar «en las demas tareas»."""
    fuente = (RAIZ / "engine" / "orchestrator.py").read_text(encoding="utf-8")
    asignaciones = [l.strip() for l in fuente.splitlines()
                    if "nemotron-mini" in l and "=" in l and not l.strip().startswith("#")]
    assert not asignaciones, "nemotron-mini asignado como modelo:\n  " + "\n  ".join(asignaciones)


def test_el_capitan_cabe_de_sobra(perfil):
    """El capitan corre en TODA tarea: su huella es un coste fijo."""
    m = perfil["capitan"]["model"]
    assert huella(m, 4096) < 3.0, (
        f"{m} a 4096 mide {huella(m, 4096):.1f} GiB; el capitan se paga en cada "
        f"encargo y por encima de ~2,5 no cabe entero en la VRAM de 4 GiB")


# ─── freno de estancamiento ───────────────────────────────────────────────────
# El 2026-09-24 la tarea `horas_a_segundos` giro unas cinco rondas (124 min) sin
# que el freno disparara, las dos ultimas con el MISMO codigo, mientras el
# arbitro la puntuaba en 8-10. (Primero lo conte como «quince rondas»: cada
# ronda deja unas tres escrituras de codigo en el .concilio.)
#
# Causa: el freno comparaba `final_round_score > mejor_score`, estricto y sin
# margen. La desviacion tipica medida del arbitro sobre cuatro corridas del
# mismo encargo es 6,9 puntos (62, 75, 78, 72), asi que el azar producia
# "mejoras" --- en esa corrida hubo una ronda con 0 y otra con 8, y ese 8>0
# reiniciaba el contador. El comentario del bloque CITABA esa medicion del
# ruido y la comparacion la ignoraba.

def test_una_subida_menor_que_el_ruido_no_es_mejora():
    from engine.orchestrator import ConsensusOrchestrator as O
    m = O._MARGEN_MEJORA
    assert not O._es_mejora(73, 72, m), "un punto no se distingue del azar"
    assert not O._es_mejora(78, 72, m), "6 puntos siguen por debajo de sigma=6,9"
    assert not O._es_mejora(79, 72, m), "7 puntos es justo el ruido, no lo supera"


def test_una_subida_real_si_es_mejora():
    from engine.orchestrator import ConsensusOrchestrator as O
    m = O._MARGEN_MEJORA
    assert O._es_mejora(80, 72, m), "8 puntos superan el ruido"
    assert O._es_mejora(95, 40, m)


def test_el_margen_cubre_el_ruido_medido():
    """sigma medida = 6,9. Un margen por debajo deja pasar el azar."""
    from engine.orchestrator import ConsensusOrchestrator as O
    assert O._MARGEN_MEJORA >= 7, (
        f"margen {O._MARGEN_MEJORA} por debajo de la desviacion tipica medida "
        f"(6,9): el freno vuelve a ser derrotable por ruido")


def test_el_mismo_entregable_da_la_misma_firma():
    from engine.orchestrator import ConsensusOrchestrator as O
    a = O._firma_entregable("def f(x):\n    return x + 1")
    b = O._firma_entregable("  def f(x):\n    return x + 1  ")
    assert a == b, "el espacio de los extremos no debe cambiar la firma"
    assert a != O._firma_entregable("def f(x):\n    return x + 2")


def test_la_firma_de_vacio_no_cuenta_como_repeticion():
    """Dos rondas sin entregable no son «el mismo entregable»."""
    from engine.orchestrator import ConsensusOrchestrator as O
    # El bucle exige `entregable.strip()` no vacio antes de declarar repeticion;
    # esta prueba fija que la firma de vacio existe y es estable, para que ese
    # guardia sea el unico responsable de la decision.
    assert O._firma_entregable("") == O._firma_entregable("   ")
