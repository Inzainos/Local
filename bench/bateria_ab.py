"""Bateria A/B: coder actual (concilio-medium) contra qwen2.5-coder:7b.

La sustitucion de qwen se hace SOLO dentro de este script: config.yaml no se
toca. Mi vara es independiente del verificador: casos escritos a mano y
balanceados, con la linea base trivial reportada.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.orchestrator import ConsensusOrchestrator      # noqa
from vivo_ab_referencia import TAREAS, extraer, puntuar, base_trivial    # noqa

TOPE_SEGURIDAD = 8
resumen = []
for pasada, coder in (("A actual", None), ("B qwen", "qwen2.5-coder:7b")):
    for t in TAREAS:
        orq = ConsensusOrchestrator(config_path=str(Path(__file__).resolve().parents[1] / "config.yaml"))
        if coder:
            orq.coder.model = coder
            orq.coder.fallback_model = None
        orq.max_rounds = TOPE_SEGURIDAD
        print(f"\n{'='*70}\n[{pasada}] {t['nombre']}  coder={orq.coder.model}\n{'='*70}", flush=True)
        t0 = time.time()
        try:
            bb = orq.run_consensus(user_prompt=t["prompt"])
        except Exception as e:  # noqa: BLE001
            print(f"  MURIO: {type(e).__name__}: {e}", flush=True)
            resumen.append((pasada, t["nombre"], None, None, None, None, (time.time()-t0)/60, "murio"))
            continue
        dur = (time.time() - t0) / 60
        for e in bb.execution_timeline:
            if e["stage"] in ("VERIFY", "CONCILIO"):
                print(f"  {e['stage']:8} {e['message'][:190]}", flush=True)
        codigo = extraer(bb.final_synthesis or "", t["funcion"])
        res, err = puntuar(codigo, t["funcion"], t["casos"])
        base_n, _ = base_trivial(t["casos"])
        n = len(t["casos"])
        real = None if err else round(100 * res[0] / n)
        motivo = ("CONSENSO" if bb.consensus_reached else
                  "tope" if bb.concilio_rounds >= TOPE_SEGURIDAD else "freno/sin consenso")
        print(f"  -> autoscore={bb.consensus_score}  {motivo}  rondas={bb.concilio_rounds}  "
              f"{dur:.1f} min  acierto real={real if real is not None else err}%"
              f"  (base {round(100*base_n/n)}%)", flush=True)
        resumen.append((pasada, t["nombre"], bb.consensus_score, motivo,
                        bb.concilio_rounds, real, dur, err))

print(f"\n\n{'='*84}\nRESUMEN A/B\n{'='*84}")
print(f"{'pasada':10} {'tarea':18} {'auto':>5} {'cierre':>19} {'rondas':>7} {'real':>6} {'min':>6}")
print("-"*84)
for pas, nom, auto, mot, ron, real, dur, err in resumen:
    print(f"{pas:10} {nom:18} {str(auto):>5} {str(mot):>19} {str(ron):>7} "
          f"{(str(real)+'%') if real is not None else 'n/a':>6} {dur:>6.1f}")
