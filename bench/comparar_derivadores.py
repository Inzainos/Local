"""¿Qué modelo deriva mejores casos de prueba? Medido, no opinado.

POR QUE IMPORTA ESTE PUESTO
---------------------------
El valor entero del verificador ES la calidad de sus casos. Medido el
2026-09-24: gemma3:4b derivo 8 casos de los que SIETE esperaban el mismo
valor, y con ese conjunto un codigo que rechaza todo saco 88% --- por encima
del umbral --- y se declaro consenso sobre codigo roto.

LA VARA
-------
No se juzgan los casos leyendolos. Se EJECUTAN contra tres sondas de las que
conocemos la verdad:

  correcto      implementacion buena          -> deberia sacar ~100%
  roto_real     el codigo literal de hoy      -> deberia sacar poco
  constante     `return False` siempre        -> no deberia superar la base

Un conjunto util SEPARA las tres. Uno inutil les da puntuaciones parecidas.
Misma ventana (4096) para todos, para que la comparacion aisle al modelo.
"""
import json
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.base_agent import BaseExpertAgent          # noqa: E402
from engine.model_lifecycle import ModelLifecycle      # noqa: E402
from engine.verificador import (                       # noqa: E402
    MAXIMA_PROPORCION_BASE, MINIMO_CASOS,
    derivar_casos, ejecutar_verificacion,
)

ENUNCIADO = (
    "Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool "
    "que devuelva True solo si el token tiene el formato valido de la API de "
    "Telegram: identificador numerico, DOS PUNTOS, y un secreto de EXACTAMENTE "
    "35 caracteres del alfabeto [A-Za-z0-9_-]. Devuelve solo la funcion."
)

CORRECTO = '''
import re
def validar_token_telegram(token: str) -> bool:
    return bool(re.fullmatch(r"\\d+:[A-Za-z0-9_-]{35}", token or ""))
'''

# VERBATIM del log de esta noche. Cuatro fallos independientes: longitud total
# fija (43, los validos miden 46), busca un PUNTO en vez de dos puntos,
# posiciones 21/22 inventadas, y `char in 'A-Za-z0-9_'` que comprueba
# pertenencia a la CADENA literal.
ROTO_REAL = '''
def validar_token_telegram(token: str) -> bool:
    if len(token) != 43:
        return False
    if '.' not in token:
        return False
    if not token[:21].isdigit():
        return False
    if len(token[22:]) != 35 or not all(char in 'A-Za-z0-9_' for char in token[22:]):
        return False
    return True
'''

CONSTANTE = '''
def validar_token_telegram(token: str) -> bool:
    return False
'''

# Misma ventana para todos: la comparacion tiene que aislar al modelo, no
# premiar a quien mas contexto recibio. 4096 sobra para este prompt y es el
# maximo nativo de nemotron-mini.
VENTANA = 4096
CANDIDATOS = ["nemotron-mini", "llama3.2:3b", "gemma3:4b", "mistral:7b",
              "qwen2.5-coder:7b"]

SISTEMA = ("Derivas casos de prueba de un enunciado. Devuelves solo JSON. "
           "No resuelves nada.")


def probar(modelo, lifecycle):
    agente = BaseExpertAgent(
        name=f"derivador:{modelo}", role="Derivador", model=modelo,
        fallback_model=None, temperature=0.2, system_prompt=SISTEMA,
        num_predict=2500, num_ctx=VENTANA, timeout_seconds=300,
        keep_alive="5m", lifecycle=None,
    )
    lifecycle.ensure_exclusive(modelo, num_ctx=VENTANA)
    t0 = time.time()
    casos, err = derivar_casos(ENUNCIADO, lambda p: agente.generate(prompt=p))
    dur = time.time() - t0
    lifecycle.stop_model(modelo)
    if err:
        return {"modelo": modelo, "error": err, "seg": round(dur, 1)}

    sondas = {}
    for nombre, codigo in (("correcto", CORRECTO), ("roto_real", ROTO_REAL),
                           ("constante", CONSTANTE)):
        v = ejecutar_verificacion(codigo, casos)
        sondas[nombre] = {
            "crudo": v.puntuacion, "util": v.puntuacion_util,
            "base": v.linea_base, "total": v.total,
            "discrimina": v.discrimina, "error": v.error,
        }
    return {"modelo": modelo, "seg": round(dur, 1), "n_casos": len(casos),
            "sondas": sondas, "casos": [c.as_dict() for c in casos]}


if __name__ == "__main__":
    lc = ModelLifecycle()
    res = []
    for m in CANDIDATOS:
        print(f"\n{'='*66}\n{m}\n{'='*66}", flush=True)
        try:
            r = probar(m, lc)
        except Exception as e:  # noqa: BLE001
            r = {"modelo": m, "error": f"{type(e).__name__}: {e}"}
        res.append(r)
        if "error" in r:
            print(f"  FALLO: {r['error']}", flush=True)
            continue
        s = r["sondas"]
        print(f"  {r['n_casos']} casos en {r['seg']}s  "
              f"(base {s['correcto']['base']}/{s['correcto']['total']}, "
              f"discrimina={s['correcto']['discrimina']})", flush=True)
        for n in ("correcto", "roto_real", "constante"):
            d = s[n]
            print(f"    {n:10} crudo={d['crudo']:3}%  util={d['util']:3}%"
                  + (f"  [{d['error'][:40]}]" if d["error"] else ""), flush=True)
        sep = s["correcto"]["util"] - s["roto_real"]["util"]
        print(f"    SEPARACION correcto-roto: {sep:+d} puntos", flush=True)

    with open(Path(__file__).resolve().parent / "resultados" / "derivadores.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    print(f"\n\n{'='*72}\nRESUMEN --- quien deriva casos utiles\n{'='*72}")
    print(f"{'modelo':18} {'casos':>6} {'base':>7} {'disc':>5} "
          f"{'correcto':>9} {'roto':>6} {'const':>6} {'separa':>7} {'seg':>6}")
    print("-"*72)
    for r in res:
        if "error" in r:
            print(f"{r['modelo']:18} {'--':>6}  {r['error'][:44]}")
            continue
        s = r["sondas"]
        c, ro, co = s["correcto"], s["roto_real"], s["constante"]
        print(f"{r['modelo']:18} {r['n_casos']:>6} "
              f"{c['base']}/{c['total']:<5} {str(c['discrimina'])[:5]:>5} "
              f"{c['util']:>8}% {ro['util']:>5}% {co['util']:>5}% "
              f"{c['util']-ro['util']:>+7} {r['seg']:>6}")
    print("-"*72)
    print(f"  Un conjunto sirve si: discrimina=True (base <= "
          f"{MAXIMA_PROPORCION_BASE:.0%}, >= {MINIMO_CASOS} casos),")
    print("  el correcto saca alto, y el roto y la constante sacan bajo.")
