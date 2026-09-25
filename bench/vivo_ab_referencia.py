"""Prueba EN VIVO del verificador: el Concilio resuelve, yo mido por fuera.

QUE SE PONE A PRUEBA
--------------------
El 2026-09-24 el mismo encargo, tres veces, dio autoscore 92/93/96 con
acierto real 78/38/78. La brecha llegaba a +55 puntos. Ahora que el
arbitro EJECUTA en vez de LEER, la prediccion falsable es que esa brecha
se colapse.

MI VARA ES INDEPENDIENTE de la del verificador: el verificador deriva sus
casos con un modelo; los mios estan escritos a mano y BALANCEADOS, con la
linea base trivial reportada. Si ambas concuerdan, concuerdan por acierto,
no por construccion.
"""
import json
import os
import re
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])

from engine.orchestrator import ConsensusOrchestrator  # noqa: E402

TAREAS = [
    {
        "nombre": "validar_token",
        "funcion": "validar_token_telegram",
        "prompt": (
            "Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool "
            "que devuelva True solo si el token tiene el formato valido de la API de "
            "Telegram: identificador numerico, DOS PUNTOS, y un secreto de EXACTAMENTE "
            "35 caracteres del alfabeto [A-Za-z0-9_-]. Devuelve solo la funcion."
        ),
        "casos": [
            ("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo", True),
            ("8460857489:AAHD_t4GAFOuPXXs5p022EddxDSC67e7vVw", True),
            ("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi", True),
            ("99:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", True),
            ("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdoX", False),
            ("8460857489:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUd", False),
            ("abc:AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo", False),
            ("8460857489.AAEQkX3PMiZvPw7W8Fwtx9HhotZmBZqwUdo", False),
        ],
    },
    {
        "nombre": "horas_a_segundos",
        "funcion": "a_segundos",
        "prompt": (
            "Escribe una funcion Python llamada a_segundos(texto: str) -> int que "
            "convierta duraciones como '2h', '30m', '45s', '1h30m' a segundos totales. "
            "Devuelve 0 si el texto no es una duracion valida. Devuelve solo la funcion."
        ),
        "casos": [
            ("2h", 7200), ("30m", 1800), ("45s", 45), ("1h30m", 5400),
            ("", 0), ("hola", 0), ("h", 0), ("1x", 0),
        ],
    },
]


def extraer(texto: str, nombre: str) -> str:
    for b in re.findall(r"```(?:python)?\s*(.*?)```", texto, re.S):
        if f"def {nombre}" in b:
            return b
    m = re.search(rf"(def {nombre}.*?)(?:\n\n\n|\Z)", texto, re.S)
    return m.group(1) if m else ""


def puntuar(codigo, nombre, casos):
    if not codigo.strip():
        return None, "no se extrajo funcion"
    ns = {}
    try:
        exec(compile(codigo, "<c>", "exec"), ns)
    except Exception as e:
        return None, f"no compila: {type(e).__name__}: {e}"
    f = ns.get(nombre)
    if not callable(f):
        return None, f"{nombre} no quedo definida"
    ok, detalle = 0, []
    for entrada, esperado in casos:
        try:
            obtenido = f(entrada)
        except Exception as e:
            obtenido = f"EXC:{type(e).__name__}"
        correcto = obtenido == esperado
        ok += correcto
        detalle.append((entrada, esperado, obtenido, correcto))
    return (ok, detalle), None


def base_trivial(casos):
    from collections import Counter
    val, n = Counter(e for _, e in casos).most_common(1)[0]
    return n, val


if __name__ == "__main__":
    orq = ConsensusOrchestrator(config_path="config.yaml")
    print(f"coder={orq.coder.model}  arbitro={orq.optimizer.model}  "
          f"umbral={orq.threshold if hasattr(orq,'threshold') else '?'}\n", flush=True)
    resumen = []

    for t in TAREAS:
        print(f"\n{'='*70}\nTAREA: {t['nombre']}\n{'='*70}", flush=True)
        t0 = time.time()
        try:
            bb = orq.run_consensus(user_prompt=t["prompt"])
        except Exception as e:
            print(f"  LA CORRIDA MURIO: {type(e).__name__}: {e}", flush=True)
            resumen.append((t["nombre"], None, None, 0, len(t["casos"]),
                            (time.time()-t0)/60, f"murio: {type(e).__name__}"))
            continue
        dur = (time.time() - t0) / 60

        # --- lo que hizo el VERIFICADOR, en sus propias palabras ---
        verify = [e for e in bb.execution_timeline if e["stage"] == "VERIFY"]
        print(f"\n  --- eventos del verificador ({len(verify)}) ---", flush=True)
        for e in verify:
            print(f"    {e['message'][:220]}", flush=True)
        if not verify:
            print("    NINGUNO: el verificador no actuo en esta tarea", flush=True)

        codigo = extraer(bb.final_synthesis or "", t["funcion"])
        res, err = puntuar(codigo, t["funcion"], t["casos"])
        base_n, base_val = base_trivial(t["casos"])
        n = len(t["casos"])

        print(f"\n  autoscore  : {bb.consensus_score}/100 "
              f"({'CONSENSO' if bb.consensus_reached else 'SIN consenso'}, "
              f"{bb.concilio_rounds} rondas, {dur:.1f} min)", flush=True)
        if err:
            print(f"  MI VARA    : FALLO -> {err}", flush=True)
            resumen.append((t["nombre"], bb.consensus_score, None, base_n, n, dur, err))
            print((bb.final_synthesis or "")[:600], flush=True)
            continue

        ok, detalle = res
        real = round(100*ok/n)
        print(f"  acierto real: {ok}/{n} = {real}%", flush=True)
        print(f"  linea base  : {base_n}/{n} = {round(100*base_n/n)}% "
              f"(devolviendo siempre {base_val!r})", flush=True)
        print(f"  {'POR ENCIMA de la base' if ok > base_n else 'NO SUPERA la base trivial'}",
              flush=True)
        print(f"  BRECHA autoscore-real: {bb.consensus_score - real:+d} puntos", flush=True)
        for entrada, esp, obt, c in detalle:
            if not c:
                print(f"     falla: {str(entrada)[:44]!r} -> {obt!r} (esperado {esp!r})",
                      flush=True)
        resumen.append((t["nombre"], bb.consensus_score, ok, base_n, n, dur, None))
        print("\n  --- codigo ---", flush=True)
        print("  " + "\n  ".join(codigo[:700].splitlines()), flush=True)

    print(f"\n\n{'='*70}\nRESUMEN\n{'='*70}")
    print(f"{'tarea':20} {'autoscore':>10} {'real':>6} {'base':>6} {'brecha':>7} {'min':>6}")
    print("-"*70)
    for nom, auto, ok, base, n, dur, err in resumen:
        if ok is None:
            print(f"{nom:20} {str(auto):>10} {'n/a':>6} {100*base//n:>5}% {'n/a':>7} {dur:>6.1f}  {err}")
        else:
            real = round(100*ok/n)
            print(f"{nom:20} {auto:>10} {real:>5}% {100*base//n:>5}% "
                  f"{auto-real:>+7} {dur:>6.1f}")
    print("\nREFERENCIA (antes del verificador, mismo encargo validar_token):")
    print("  corrida 1: autoscore 92, real 78  -> brecha +14")
    print("  corrida 2: autoscore 93, real 38  -> brecha +55")
    print("  corrida 3: autoscore 96, real 78  -> brecha +18")
