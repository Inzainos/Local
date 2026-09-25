"""Huella real = peso + cache KV. Parametros leidos de /api/show, no a mano.

CACHE KV = 2 (K y V) x capas x kv_heads x head_dim x ctx x 2 bytes (f16).
Escala LINEAL con ctx: pedir la ventana completa multiplica el gasto ~8x
frente a 16384.

DOS TRAMPAS QUE ME COMI HOY
---------------------------
1. head_dim NO es siempre emb/heads. gemma3 declara key_length=256 mientras
   emb/heads da 320: derivarlo sobreestima su cache un 25%. Se usa el
   declarado cuando existe.
2. gemma3 lleva sliding_window=1024. En Gemma 3 la mayoria de las capas
   atienden solo una ventana local, asi que su cache real es una fraccion
   de la formula plena. No se cuantas capas son locales --- el manifiesto no
   lo dice --- asi que aqui se da la COTA ALTA y se marca para MEDIR.
"""
from pathlib import Path
import json
import subprocess

GiB = 2**30
SOBRECARGA = 1.05   # buffers de computo; ajustado contra tres medidas reales
HOST_GIB = 11.71    # Win32_ComputerSystem.TotalPhysicalMemory. `free` de WSL
                    # dice 7 GiB porque no ve el host donde corre Ollama.

MODELOS = ["llama3.2:3b", "nemotron-mini:latest", "gemma3:4b", "mistral:7b",
           "qwen2.5-coder:7b", "deepseek-r1:8b", "deepseek-r1:14b"]


def _curl(url, data=None):
    cmd = ["curl", "-s", url]
    if data:
        cmd += ["-d", json.dumps(data)]
    return json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)


pesos = {m["name"]: m["size"] / GiB
         for m in _curl("http://127.0.0.1:11434/api/tags").get("models", [])}

info = {}
for m in MODELOS:
    i = _curl("http://127.0.0.1:11434/api/show", {"model": m}).get("model_info", {})

    def g(suf):
        for k, v in i.items():
            if k.endswith(suf):
                return v
        return None

    heads, emb = g("attention.head_count"), g("embedding_length")
    kl = g("attention.key_length")
    info[m] = {
        "capas": g("block_count"),
        "kvh": g("attention.head_count_kv"),
        "hd": kl if kl else (emb // heads if emb and heads else None),
        "hd_declarado": kl is not None,
        "sliding": g("attention.sliding_window"),
        "ventana": g("context_length"),
        "peso": pesos.get(m, 0.0),
    }


def cache(m, ctx):
    d = info[m]
    return 2 * d["capas"] * d["kvh"] * d["hd"] * ctx * 2 / GiB


def total(m, ctx):
    return (info[m]["peso"] + cache(m, ctx)) * SOBRECARGA


# ─── validacion contra lo medido HOY ────────────────────────────────────────
MEDIDO = [("llama3.2:3b", 16384, 3.80, "concilio-investigador en vivo"),
          ("deepseek-r1:8b", 16384, 7.28, "concilio-medium en vivo"),
          ("deepseek-r1:8b", 131072, 23.93, "antes de acotar num_ctx")]
print("VALIDACION --- calculado contra medido con /api/ps")
print("-" * 72)
for m, ctx, med, nota in MEDIDO:
    cal = total(m, ctx)
    err = 100 * (cal - med) / med
    print(f"  {m:16} @{ctx:<6}  calc {cal:6.2f}  medido {med:6.2f} GiB  "
          f"error {err:+5.1f}%   ({nota})")

print("\nHUELLA TOTAL EN GiB (peso + cache KV), por ventana ASIGNADA")
print("-" * 82)
CTXS = [4096, 8192, 16384, 32768, 131072]
print(f"{'modelo':22} {'peso':>5} {'hd':>4} " + " ".join(f"{c:>8}" for c in CTXS))
print("-" * 82)
for m in MODELOS:
    d = info[m]
    fila = []
    for c in CTXS:
        if c > d["ventana"]:
            fila.append(f"{'--':>8}")
        else:
            t = total(m, c)
            fila.append(f"{t:7.1f}" + ("!" if t >= HOST_GIB else " "))
    marca = "*" if d["sliding"] else " "
    print(f"{m:22} {d['peso']:5.2f} {d['hd']:>4} " + " ".join(fila) + f"  {marca}")
print("-" * 82)
print(f"  '!' no cabe en el host ({HOST_GIB:.2f} GiB TOTALES, con Windows y")
print("      Sentinel Omega encima: el techo UTIL es bastante menor).")
print("  '*' lleva sliding window: la cifra es COTA ALTA, su cache real es menor.")
print("      MEDIR antes de dimensionar un nivel con este modelo.")

# ─── VENTANA MAXIMA QUE CABE EN EL PRESUPUESTO ──────────────────────────────
# Presupuesto medido el 2026-09-24 con la corrida en vivo:
#   host 11.71  =  Windows 2.02 + WSL/Sentinel 1.95 + Ollama 7.28 + libre 0.46
PRESUPUESTO = 7.3     # GiB para UN modelo, con Sentinel Omega corriendo
MARGEN = 6.8          # el mismo dejando algo de aire
SIN_SENTINEL = 9.2    # deteniendo Sentinel (libera ~1.95, pero Windows sigue)

print("\n\nVENTANA MAXIMA POR MODELO, segun presupuesto")
print("-" * 76)
print(f"{'modelo':22} {'ctx max @6.8':>13} {'@7.3 (al borde)':>16} {'@9.2 sin Sentinel':>18}")
print("-" * 76)
ESCALA = [2048, 4096, 8192, 12288, 16384, 24576, 32768, 49152, 65536, 98304, 131072]
for m in MODELOS:
    fila = []
    for techo in (MARGEN, PRESUPUESTO, SIN_SENTINEL):
        cabe = [c for c in ESCALA if c <= info[m]["ventana"] and total(m, c) <= techo]
        fila.append(f"{max(cabe) if cabe else 'NO CABE':>13}")
    print(f"{m:22} " + " ".join(f"{x:>15}" for x in fila))
print("-" * 76)
print("  Un 'NO CABE' aqui significa que el modelo no entra NI con la ventana")
print("  minima: cargarlo manda a disco y la etapa se vuelve intratable.")
