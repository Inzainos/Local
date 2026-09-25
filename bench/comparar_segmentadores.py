"""¿Quien segmenta mejor? Hechos clave escritos a mano, cobertura medida.

Por cada enunciado, una lista de HECHOS (patrones regex, sin mayusculas) que
una buena segmentacion tiene que recoger en algun campo. Cobertura = hechos
presentes / hechos totales. Ademas: reglas descartadas por traer numeros que
el enunciado no dice (calcular en vez de reescribir) y tiempo.
"""
from pathlib import Path
import re, sys, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.model_lifecycle import ModelLifecycle   # noqa
from engine.segmentacion import segmentar           # noqa
from engine.tool_agent import run_with_tools        # noqa

FIN = ""
ENUNCIADOS = {
 "validar_token": ("Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool que "
   "devuelva True solo si el token tiene el formato valido de la API de Telegram: identificador "
   "numerico, DOS PUNTOS, y un secreto de EXACTAMENTE 35 caracteres del alfabeto [A-Za-z0-9_-].",
   [r"\b35\b", r"dos puntos|['\"`]:['\"`]", r"a-za-z0-9_-", r"num[eé]ric|d[ií]git"]),
 "a_segundos": ("Escribe una funcion Python llamada a_segundos(texto: str) -> int que convierta "
   "duraciones como '2h', '30m', '45s', '1h30m' a segundos totales. Devuelve 0 si el texto no es "
   "una duracion valida.",
   [r"\bh\b|hora", r"\bm\b|minuto", r"\bs\b|segundo", r"1h30m|combin|compuest|varias unidades",
    r"\b0\b"]),
 "es_palindromo": ("Escribe una funcion Python llamada es_palindromo(texto: str) -> bool que devuelva "
   "True si el texto es palindromo ignorando mayusculas, espacios y signos de puntuacion. La cadena "
   "vacia devuelve True.",
   [r"may[uú]scul", r"espacio", r"puntuaci|signos", r"vac[ií]a"]),
 "es_matricula": ("Escribe una funcion Python llamada es_matricula(s: str) -> bool que devuelva True "
   "solo si s tiene tres letras mayusculas, un guion y cuatro digitos, por ejemplo ABC-1234.",
   [r"\btres\b|\b3\b", r"may[uú]scul", r"gui[oó]n|['\"`]-['\"`]", r"\bcuatro\b|\b4\b", r"d[ií]git"]),
 "es_bisiesto": ("Escribe una funcion Python llamada es_bisiesto(anio: int) -> bool con la regla "
   "gregoriana: divisible entre 4, salvo los divisibles entre 100 que no lo sean entre 400.",
   [r"\b4\b|cuatro", r"\b100\b", r"\b400\b"]),
 "a_romano": ("Escribe una funcion Python llamada a_romano(n: int) -> str que convierta un entero de "
   "1 a 3999 a numeros romanos en mayusculas, con notacion sustractiva (4 es IV, 9 es IX).",
   [r"3999", r"sustractiv|\biv\b|\bix\b", r"may[uú]scul"]),
 "es_ipv4": ("Escribe una funcion Python llamada es_ipv4(s: str) -> bool que devuelva True solo si s es "
   "una direccion IPv4 en notacion decimal: cuatro numeros de 0 a 255 separados por puntos.",
   [r"\bcuatro\b|\b4\b", r"255", r"punto"]),
}
TOTAL = sum(len(h) for _, h in ENUNCIADOS.values())
CANDIDATOS = ["llama3.2:3b", "gemma3:4b", "mistral:7b", "qwen2.5-coder:7b", "codegemma:7b"]
SISTEMA = "Segmentas enunciados. Devuelves solo JSON. No resuelves nada."

lc = ModelLifecycle()
resumen = []
for m in CANDIDATOS:
    lc.stop_all_except(keep=None); time.sleep(2)
    lc.ensure_exclusive(m, num_ctx=4096)
    inv = lambda p, e, m=m: run_with_tools(model=m, system_prompt=SISTEMA, user_prompt=p,
        ollama_host="http://127.0.0.1:11434", tools_schema=None, tool_impls=None,
        max_iterations=1, num_ctx=4096, format_schema=e, temperature=0.0)
    cubiertos, descart, t0, faltan = 0, 0, time.time(), []
    for nombre, (enunciado, hechos) in ENUNCIADOS.items():
        seg = segmentar(enunciado, inv)
        texto = seg.texto().lower()
        for h in hechos:
            if re.search(h, texto):
                cubiertos += 1
            else:
                faltan.append(f"{nombre}:{h[:14]}")
        descart += len(seg.descartadas)
    seg_t = time.time() - t0
    resumen.append((m, cubiertos, descart, seg_t, faltan))
    print(f"{m:18} cobertura {cubiertos:2}/{TOTAL}  descartadas {descart}  {seg_t:5.0f}s  "
          f"faltan: {faltan[:5]}", flush=True)
lc.stop_all_except(keep=None)
print("\nORDEN (cobertura, menos descartadas, mas rapido):")
for m, c, d, t, _ in sorted(resumen, key=lambda r: (-r[1], r[2], r[3])):
    print(f"  {m:18} {c}/{TOTAL}  descartadas={d}  {t:.0f}s")
