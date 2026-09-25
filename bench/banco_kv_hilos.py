"""Banco de medida: velocidad por num_thread y calidad con verdad sabida.

Se corre ANTES y DESPUES de cambiar la cache KV a q8_0. Sin la linea base,
«va mas rapido» no se puede afirmar, y «no degrada» tampoco.

  velocidad  prompt_tps  = procesar el prompt (depende del COMPUTO)
             gen_tps     = generar tokens (depende del ANCHO DE BANDA)
  calidad    el modelo escribe validar_token_telegram a temperatura 0 y el
             verificador por especificacion lo puntua (util sobre la base)
"""
from pathlib import Path
import json, re, sys, time
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.especificacion import parsear_formato, casos_desde_formato  # noqa
from engine.model_lifecycle import ModelLifecycle                        # noqa
from engine.verificador import ejecutar_verificacion                     # noqa

H = "http://127.0.0.1:11434"
ETIQUETA = sys.argv[1] if len(sys.argv) > 1 else "base"
ENUNCIADO = ("Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool "
             "que devuelva True solo si el token tiene el formato valido de la API de "
             "Telegram: identificador numerico, DOS PUNTOS, y un secreto de EXACTAMENTE "
             "35 caracteres del alfabeto [A-Za-z0-9_-]. Devuelve solo la funcion en un "
             "bloque de codigo.")
SPEC = {"aplica": True, "funcion": "validar_token_telegram", "partes": [
    {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 1, "longitud_max": 0},
    {"tipo": "separador", "texto": ":"},
    {"tipo": "campo", "alfabeto": "A-Za-z0-9_-", "longitud_min": 35, "longitud_max": 35}]}
CASOS = casos_desde_formato(parsear_formato(SPEC, ENUNCIADO)[0])
PROMPT_LARGO = ("Resume en una frase el siguiente registro de eventos.\n"
                + "\n".join(f"2026-09-24 20:{i%60:02d}:{i%60:02d} | sensor_{i%17} | "
                            f"lectura={i*37%997} umbral=500 estado={'ALTA' if i*37%997>500 else 'ok'}"
                            for i in range(110)))

def gen(modelo, prompt, ctx, npred, opciones=None):
    o = {"temperature": 0.0, "num_ctx": ctx, "num_predict": npred, "seed": 7}
    o.update(opciones or {})
    with httpx.Client(timeout=1200) as c:
        r = c.post(f"{H}/api/generate", json={"model": modelo, "prompt": prompt,
                   "stream": False, "keep_alive": "5m", "options": o}).json()
    return r

def tps(n, ns):
    return round(n / (ns / 1e9), 2) if n and ns else 0.0

def vram(modelo):
    for m in httpx.get(f"{H}/api/ps").json().get("models", []):
        if m["name"].split(":")[0] == modelo.split(":")[0]:
            return round(m["size"]/2**30, 2), round(m.get("size_vram", 0)/2**30, 2)
    return None, None

lc = ModelLifecycle()
res = {"etiqueta": ETIQUETA, "hilos": [], "calidad": []}

# ── 1. HILOS, en el cuello de botella ──────────────────────────────────────
M = "concilio-medium"
for hilos in (8, 12):
    lc.stop_all_except(keep=None); time.sleep(2)
    gen(M, "hola", 16384, 4, {"num_thread": hilos})           # carga + calentamiento
    medidas = []
    for _ in range(2):
        # Prefijo UNICO: sin el, la segunda repeticion se servia de la cache de
        # prefijos y el prompt salia a ~7.000 tok/s --- imposible en esta GPU.
        import uuid
        r = gen(M, f"[corrida {uuid.uuid4()}]\n" + PROMPT_LARGO, 16384, 96,
                {"num_thread": hilos})
        medidas.append((tps(r.get("prompt_eval_count"), r.get("prompt_eval_duration")),
                        tps(r.get("eval_count"), r.get("eval_duration")),
                        r.get("prompt_eval_count")))
    total, en_vram = vram(M)
    fila = {"hilos": hilos,
            "prompt_tps": round(sum(m[0] for m in medidas)/2, 2),
            "gen_tps": round(sum(m[1] for m in medidas)/2, 2),
            "prompt_tokens": medidas[0][2], "gib": total, "vram_gib": en_vram}
    res["hilos"].append(fila)
    print(f"[{ETIQUETA}] hilos={hilos:2}  prompt={fila['prompt_tps']:6} tok/s  "
          f"gen={fila['gen_tps']:5} tok/s  ({fila['prompt_tokens']} tok de prompt)  "
          f"{total} GiB, {en_vram} en VRAM", flush=True)

# ── 2. CALIDAD con verdad sabida ────────────────────────────────────────────
for modelo, npred in (("qwen2.5-coder:7b", 800),):
    lc.stop_all_except(keep=None); time.sleep(2)
    t0 = time.time()
    r = gen(modelo, ENUNCIADO, 16384, npred)
    txt = r.get("response", "")
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S)
    bloques = [b for b in re.findall(r"```(?:python)?\s*(.*?)```", txt, re.S)
               if "def validar_token_telegram" in b]
    codigo = bloques[0] if bloques else ""
    v = ejecutar_verificacion(codigo, CASOS) if codigo else None
    fila = {"modelo": modelo, "util": v.puntuacion_util if v else None,
            "crudo": v.puntuacion if v else None,
            "error": (v.error if v else "sin codigo extraible"),
            "gen_tps": tps(r.get("eval_count"), r.get("eval_duration")),
            "seg": round(time.time()-t0, 1), "codigo": codigo[:600]}
    res["calidad"].append(fila)
    print(f"[{ETIQUETA}] calidad {modelo:18} util={fila['util']}  crudo={fila['crudo']}  "
          f"gen={fila['gen_tps']} tok/s  {fila['seg']}s  {fila['error'] or ''}", flush=True)

# ── 3. EXTRACCION determinista: con la cache cambiada debe salir IDENTICA ──
from engine.especificacion import extraer_formato, ESQUEMA_FORMATO  # noqa
from engine.tool_agent import run_with_tools                         # noqa
lc.stop_all_except(keep=None)
lc.ensure_exclusive("qwen2.5-coder:7b", num_ctx=4096)
salidas = []
for _ in range(3):
    crudo = {}
    def inv(p, e):
        crudo["t"] = run_with_tools(model="qwen2.5-coder:7b",
            system_prompt="Describes formatos. Devuelves solo JSON. No resuelves nada.",
            user_prompt=p, ollama_host=H, tools_schema=None, tool_impls=None,
            max_iterations=1, num_ctx=4096, format_schema=e, temperature=0.0)
        return crudo["t"]
    fmt, err = extraer_formato(ENUNCIADO, inv)
    salidas.append(crudo.get("t", ""))
res["extraccion"] = salidas
print(f"[{ETIQUETA}] extraccion: {len(set(salidas))} salida(s) distinta(s) en 3 "
      f"intentos; spec {'OK' if fmt else 'RECHAZADA: ' + err[:50]}", flush=True)

lc.stop_all_except(keep=None)
with open(Path(__file__).resolve().parent / "resultados" / f"banco_{ETIQUETA}.json", "w") as f:
    json.dump(res, f, indent=1, ensure_ascii=False)
print(f"[{ETIQUETA}] listo", flush=True)
