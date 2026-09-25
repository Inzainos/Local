"""Bateria de ACEPTACION de la v1: las 7 tareas por run_consensus REAL.

Nada simulado: configuracion real, modelos reales, verificador real. Mi vara
(casos escritos a mano) juzga el codigo entregado de forma independiente.

Criterio de la v1:
  - VERIFICADO solo si el codigo es correcto (mi vara lo confirma).
  - Ningun «verificado» sobre codigo roto: cero consensos falsos.
  - SIN VERIFICAR solo donde el enunciado no admite casos fiables.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.orchestrator import ConsensusOrchestrator   # noqa
from engine.verificador import extraer_codigo           # noqa
from tareas_ref import TAREAS, FIN                      # noqa

def mi_vara(texto, fn, casos):
    codigo = extraer_codigo(texto or "", fn)
    if not codigo:
        return None
    ns = {}
    try:
        exec(compile(codigo, "<c>", "exec"), ns); f = ns[fn]
    except Exception:
        return 0
    ok = 0
    for x, e in casos:
        try: ok += f(x) == e
        except Exception: pass
    return ok

# Uso: aceptacion.py [tarea ...]  --- sin argumentos corre las siete.
SOLO = set(sys.argv[1:])
filas = []
for nombre, fn, prompt, casos in TAREAS:
    if SOLO and nombre not in SOLO:
        continue
    orq = ConsensusOrchestrator(config_path=str(Path(__file__).resolve().parents[1] / "config.yaml"))
    orq.max_rounds = 6            # tope de seguridad solo si se escala al concilio
    t0 = time.time()
    try:
        bb = orq.run_consensus(user_prompt=prompt.replace(FIN, ""))
    except Exception as e:  # noqa: BLE001
        print(f"{nombre:14} MURIO: {type(e).__name__}: {e}", flush=True)
        filas.append((nombre, "MURIO", None, len(casos), (time.time()-t0)/60)); continue
    via = bb.shared_notes.get("via") or ("concilio: CONSENSO" if bb.consensus_reached else "concilio: sin consenso")
    ok = mi_vara(bb.final_synthesis, fn, casos)
    dur = (time.time() - t0) / 60
    filas.append((nombre, via, ok, len(casos), dur))
    for e in bb.execution_timeline:
        if e["stage"] in ("DIRECTO",):
            print(f"   {e['message'][:150]}", flush=True)
    print(f"{nombre:14} {via:24} mi vara: {ok if ok is not None else 'sin codigo'}/{len(casos)}  {dur:.1f} min", flush=True)

print(f"\n{'='*78}\nACEPTACION v1\n{'='*78}")
falsos = 0
for nombre, via, ok, n, dur in filas:
    correcto = ok == n
    alerta = ""
    if via in ("directa_verificada", "concilio: CONSENSO") and not correcto:
        alerta = "   <<< CONSENSO FALSO"; falsos += 1
    print(f"  {nombre:14} {via:24} {('correcto' if correcto else f'{ok}/{n}'):>9}  {dur:5.1f} min{alerta}")
print(f"\n  consensos falsos: {falsos}   tiempo total: {sum(f[4] for f in filas):.1f} min")
