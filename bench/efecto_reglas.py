"""¿Las reglas segmentadas mejoran al coder? Con y sin, mismas condiciones."""
from pathlib import Path
import re, sys, time, httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.model_lifecycle import ModelLifecycle                  # noqa
from engine.segmentacion import segmentar, bloque_para_coder       # noqa
from engine.tool_agent import run_with_tools                       # noqa
from engine.verificador import extraer_codigo                      # noqa
from tareas_ref import TAREAS, ENUNCIADOS                         # noqa
H = "http://127.0.0.1:11434"
FIN = " Devuelve solo la funcion en un bloque de codigo."
lc = ModelLifecycle()

# 1) segmentar las siete con qwen, defensa corregida
lc.stop_all_except(keep=None); lc.ensure_exclusive("qwen2.5-coder:7b", num_ctx=4096)
reglas, cubiertos, total, descart = {}, 0, 0, 0
for nombre, fn, prompt, casos in TAREAS:
    enunciado = prompt.replace(FIN, "")
    seg = segmentar(enunciado, lambda p, e: run_with_tools(model="qwen2.5-coder:7b",
        system_prompt="Segmentas enunciados. Devuelves solo JSON. No resuelves nada.",
        user_prompt=p, ollama_host=H, tools_schema=None, tool_impls=None, max_iterations=1,
        num_ctx=4096, format_schema=e, temperature=0.0))
    reglas[nombre] = bloque_para_coder(seg)
    hechos = ENUNCIADOS[nombre][1]
    cubiertos += sum(bool(re.search(h, seg.texto().lower())) for h in hechos)
    total += len(hechos); descart += len(seg.descartadas)
print(f"segmentacion qwen (defensa corregida): cobertura {cubiertos}/{total}, "
      f"descartadas {descart}", flush=True)

def evaluar(modelo, prompt, fn, casos):
    with httpx.Client(timeout=900) as c:
        r = c.post(f"{H}/api/generate", json={"model": modelo, "prompt": prompt, "stream": False,
                   "keep_alive": "5m", "options": {"temperature": 0.0, "num_ctx": 8192,
                                                   "num_predict": 1200, "seed": 7}}).json()
    codigo = extraer_codigo(r.get("response", ""), fn)
    if not codigo:
        return 0
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

# 2) cada coder, sin y con reglas
res = {}
for modelo in ("codegemma:7b", "qwen2.5-coder:7b"):
    lc.stop_all_except(keep=None); time.sleep(2); lc.ensure_exclusive(modelo, num_ctx=8192)
    for nombre, fn, prompt, casos in TAREAS:
        enunciado = prompt.replace(FIN, "")
        sin = evaluar(modelo, prompt, fn, casos)
        con = evaluar(modelo, enunciado + "\n\n" + reglas[nombre] + "\n\n" + FIN.strip(), fn, casos)
        res[(modelo, nombre)] = (sin, con, len(casos))
        marca = "  <-- mejora" if con > sin else ("  <-- EMPEORA" if con < sin else "")
        print(f"{modelo:18} {nombre:14} sin {sin:2}/{len(casos):<2}  con {con:2}/{len(casos):<2}{marca}", flush=True)
lc.stop_all_except(keep=None)
print("\nRESUMEN")
for modelo in ("codegemma:7b", "qwen2.5-coder:7b"):
    f = [v for (m, _), v in res.items() if m == modelo]
    print(f"  {modelo:18} sin reglas: {sum(1 for s,c,n in f if s==n)}/7 tareas, {sum(s for s,c,n in f)}/{sum(n for s,c,n in f)} casos"
          f"   con reglas: {sum(1 for s,c,n in f if c==n)}/7 tareas, {sum(c for s,c,n in f)}/{sum(n for s,c,n in f)} casos")
