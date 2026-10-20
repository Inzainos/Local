"""A/B del SEGUNDO intento de la via directa: mismo coder vs otro (qwen).

Origen (2026-09-25, en vivo): codegemma escribio DOS VECES el mismo codigo
fallido (`len==39 and isalnum()`) en la redaccion «que acepte...» del token.
A temperatura 0 el segundo intento con el MISMO modelo solo re-muestrea el
mismo prompt enmarcado, y si la via directa falla las dos veces la tarea
escala al concilio (25-50 min medidos, no cerro ninguna). Hipotesis: otro
coder con los casos fallidos arregla tareas que el primero no puede.

Condiciones fieles a produccion: temperatura 0, ventana 8192, semilla 7,
prompt = enunciado + realimentacion de `_realimentacion_directa` + «Devuelve
solo la funcion...», un modelo cargado a la vez (ModelLifecycle). La verdad
de cada tarea es la de `tareas_ref.py` (escrita a mano), mas las dos
redacciones «vivo» que fallaron en Telegram.

Se ejecuta al correrlo; no lo importes.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx                                       # noqa: E402
from engine.model_lifecycle import ModelLifecycle   # noqa: E402
from engine.verificador import (Caso, ejecutar_verificacion,   # noqa: E402
                                extraer_codigo)
from engine.orchestrator import ConsensusOrchestrator          # noqa: E402
from tareas_ref import TAREAS, T_TOKEN, T_MAT, fmt_casos       # noqa: E402

H = "http://127.0.0.1:11434"
FIN = " Devuelve solo la funcion en un bloque de codigo."
CODEGEMMA = "codegemma:7b"
QWEN = "qwen2.5-coder:7b"

# Las dos redacciones «vivo» que fallaron por Telegram el 25-sep (la primera
# tarea real: codegemma repitio el mismo codigo las dos veces).
T_TOKEN_VIVO = ("Escribe una funcion Python llamada validar_token_telegram"
                "(token: str) -> bool que acepte identificador numerico, DOS PUNTOS "
                "y un secreto de EXACTAMENTE 35 caracteres del alfabeto [A-Za-z0-9_-]")
T_MAT_VIVO = ("Escribe una funcion Python llamada es_matricula(s: str) -> bool "
              "que acepte tres letras mayusculas, un guion y cuatro digitos")
CASOS_TOKEN = fmt_casos(T_TOKEN, {"aplica": True, "funcion": "validar_token_telegram", "partes": [
    {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 1, "longitud_max": 0},
    {"tipo": "separador", "texto": ":"},
    {"tipo": "campo", "alfabeto": "A-Za-z0-9_-", "longitud_min": 35, "longitud_max": 35}]})
CASOS_MAT = fmt_casos(T_MAT, {"aplica": True, "funcion": "es_matricula", "partes": [
    {"tipo": "campo", "alfabeto": "A-Z", "longitud_min": 3, "longitud_max": 3},
    {"tipo": "separador", "texto": "-"},
    {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 4, "longitud_max": 4}]})

BATERIA = [(n, fn, p, [Caso(f"{fn}({x!r})", repr(e)) for x, e in casos])
           for n, fn, p, casos in TAREAS]
BATERIA += [
    ("token_vivo", "validar_token_telegram", T_TOKEN_VIVO + FIN,
     [Caso(f"validar_token_telegram({v!r})", repr(ok)) for v, ok in CASOS_TOKEN]),
    ("matricula_vivo", "es_matricula", T_MAT_VIVO + FIN,
     [Caso(f"es_matricula({v!r})", repr(ok)) for v, ok in CASOS_MAT]),
]


def generar(modelo, prompt):
    with httpx.Client(timeout=900) as c:
        r = c.post(f"{H}/api/generate", json={
            "model": modelo, "prompt": prompt, "stream": False, "keep_alive": "5m",
            "options": {"temperature": 0.0, "num_ctx": 8192,
                        "num_predict": 1200, "seed": 7}}).json()
    return r.get("response", "")


def intento(modelo, nombre, fn, prompt, casos):
    t0 = time.time()
    codigo = extraer_codigo(generar(modelo, prompt), fn)
    v = ejecutar_verificacion(codigo, casos)
    seg = time.time() - t0
    ok = v.total and not v.error and v.aciertos == v.total
    print(f"  {modelo:18} {nombre:16} {v.aciertos:2}/{v.total:<2}"
          f" {'VERIFICADA' if ok else ''}{' [' + (v.error or '')[:40] + ']' if v.error else ''}"
          f" {seg:4.0f}s", flush=True)
    return v, seg, codigo


lc = ModelLifecycle()

# ── Intento 1: codegemma, como en produccion ─────────────────────────────────
print("=== INTENTO 1 (codegemma, temperatura 0) ===", flush=True)
lc.stop_all_except(keep=None)
time.sleep(2)
lc.ensure_exclusive(CODEGEMMA, num_ctx=8192)
fallidas = []
for nombre, fn, prompt, casos in BATERIA:
    v, seg, codigo = intento(CODEGEMMA, nombre, fn, prompt, casos)
    if not (v.total and not v.error and v.aciertos == v.total):
        fallidas.append((nombre, fn, prompt, casos, v, codigo))

print(f"\n=== Fallan el intento 1: {len(fallidas)} de {len(BATERIA)} ===", flush=True)
if not fallidas:
    lc.stop_all_except(keep=None)
    sys.exit(0)

# ── Intento 2: A/B con la MISMA realimentacion de produccion ─────────────────
resultados = {}
for modelo in (CODEGEMMA, QWEN):
    print(f"\n=== INTENTO 2 con {modelo} ===", flush=True)
    lc.stop_all_except(keep=None)
    time.sleep(2)
    lc.ensure_exclusive(modelo, num_ctx=8192)
    for nombre, fn, prompt, casos, v1, _ in fallidas:
        # Fiel a produccion: enunciado sin instruccion final + realimentacion
        # + el sufijo que anade `_intentar_via_directa`.
        base = prompt[:-len(FIN)] if prompt.endswith(FIN) else prompt
        realim = ConsensusOrchestrator._realimentacion_directa(v1)
        prompt2 = (base + realim
                   + "\n\nDevuelve solo la funcion en un bloque de codigo.")
        v2, seg, _ = intento(modelo, nombre, fn, prompt2, casos)
        resultados[(modelo, nombre)] = (v2, seg)

lc.stop_all_except(keep=None)

# ── Resumen ─────────────────────────────────────────────────────────────────
print("\n=== RESUMEN: a quien arregla cada 2.º intento ===", flush=True)
for nombre, fn, prompt, casos, v1, _ in fallidas:
    fila = [f"{nombre:16} 1º {v1.aciertos}/{v1.total}"]
    for modelo in (CODEGEMMA, QWEN):
        v2, seg = resultados[(modelo, nombre)]
        arregla = (v2.total and not v2.error and v2.aciertos == v2.total)
        fila.append(f"2º {modelo.split(':')[0]}={v2.aciertos}/{v2.total}"
                    f"{' ARREGLA' if arregla else ''} ({seg:.0f}s)")
    print("  " + "  ".join(fila), flush=True)
