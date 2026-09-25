"""Muestra ampliada: 7 tareas con verdad escrita a mano, codegemma vs qwen.

Mismas condiciones: una llamada, temperatura 0, ventana 8192. Casos
balanceados cuando la salida es booleana. Se cuenta la tarea como APROBADA
solo si acierta TODOS sus casos.
"""
import sys
from pathlib import Path, time, httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.especificacion import parsear_formato, generar_valores       # noqa
from engine.model_lifecycle import ModelLifecycle                        # noqa
from engine.verificador import extraer_codigo                            # noqa
H = "http://127.0.0.1:11434"
FIN = " Devuelve solo la funcion en un bloque de codigo."

def fmt_casos(enunciado, spec):
    return generar_valores(parsear_formato(spec, enunciado)[0])

T_TOKEN = ("Escribe una funcion Python llamada validar_token_telegram(token: str) -> bool que "
           "devuelva True solo si el token tiene el formato valido de la API de Telegram: "
           "identificador numerico, DOS PUNTOS, y un secreto de EXACTAMENTE 35 caracteres "
           "del alfabeto [A-Za-z0-9_-].")
T_MAT = ("Escribe una funcion Python llamada es_matricula(s: str) -> bool que devuelva True "
         "solo si s tiene tres letras mayusculas, un guion y cuatro digitos, por ejemplo ABC-1234.")
TAREAS = [
  ("validar_token", "validar_token_telegram", T_TOKEN + FIN,
   fmt_casos(T_TOKEN, {"aplica": True, "funcion": "validar_token_telegram", "partes": [
     {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 1, "longitud_max": 0},
     {"tipo": "separador", "texto": ":"},
     {"tipo": "campo", "alfabeto": "A-Za-z0-9_-", "longitud_min": 35, "longitud_max": 35}]})),
  ("a_segundos", "a_segundos",
   "Escribe una funcion Python llamada a_segundos(texto: str) -> int que convierta duraciones "
   "como '2h', '30m', '45s', '1h30m' a segundos totales. Devuelve 0 si el texto no es una "
   "duracion valida." + FIN,
   [("2h", 7200), ("30m", 1800), ("45s", 45), ("1h30m", 5400), ("", 0), ("hola", 0), ("h", 0), ("1x", 0)]),
  ("es_palindromo", "es_palindromo",
   "Escribe una funcion Python llamada es_palindromo(texto: str) -> bool que devuelva True si "
   "el texto es palindromo ignorando mayusculas, espacios y signos de puntuacion. La cadena "
   "vacia devuelve True." + FIN,
   [("Anita lava la tina", True), ("", True), ("oso", True), ("A man, a plan, a canal: Panama", True),
    ("hola", False), ("python", False), ("Anita lava la tuna", False), ("ab", False)]),
  ("es_matricula", "es_matricula", T_MAT + FIN,
   fmt_casos(T_MAT, {"aplica": True, "funcion": "es_matricula", "partes": [
     {"tipo": "campo", "alfabeto": "A-Z", "longitud_min": 3, "longitud_max": 3},
     {"tipo": "separador", "texto": "-"},
     {"tipo": "campo", "alfabeto": "0-9", "longitud_min": 4, "longitud_max": 4}]})),
  ("es_bisiesto", "es_bisiesto",
   "Escribe una funcion Python llamada es_bisiesto(anio: int) -> bool con la regla gregoriana: "
   "divisible entre 4, salvo los divisibles entre 100 que no lo sean entre 400." + FIN,
   [(2000, True), (2024, True), (1996, True), (2400, True),
    (1900, False), (2023, False), (2100, False), (2019, False)]),
  ("a_romano", "a_romano",
   "Escribe una funcion Python llamada a_romano(n: int) -> str que convierta un entero de 1 a "
   "3999 a numeros romanos en mayusculas, con notacion sustractiva (4 es IV, 9 es IX)." + FIN,
   [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"), (90, "XC"),
    (400, "CD"), (1994, "MCMXCIV"), (3999, "MMMCMXCIX")]),
  ("es_ipv4", "es_ipv4",
   "Escribe una funcion Python llamada es_ipv4(s: str) -> bool que devuelva True solo si s es "
   "una direccion IPv4 en notacion decimal: cuatro numeros de 0 a 255 separados por puntos." + FIN,
   [("192.168.1.1", True), ("0.0.0.0", True), ("255.255.255.255", True), ("8.8.8.8", True),
    ("10.0.0.256", False), ("1.2.3", False), ("a.b.c.d", False), ("1.2.3.4.5", False)]),
]

lc = ModelLifecycle()
tabla = {}
for modelo in ("codegemma:7b", "qwen2.5-coder:7b"):
    lc.stop_all_except(keep=None); time.sleep(2)
    lc.ensure_exclusive(modelo, num_ctx=8192)
    for nombre, fn, prompt, casos in TAREAS:
        t0 = time.time()
        with httpx.Client(timeout=900) as c:
            r = c.post(f"{H}/api/generate", json={"model": modelo, "prompt": prompt, "stream": False,
                       "keep_alive": "5m", "options": {"temperature": 0.0, "num_ctx": 8192,
                                                       "num_predict": 1200, "seed": 7}}).json()
        seg = time.time() - t0
        codigo = extraer_codigo(r.get("response", ""), fn)
        ok, fallos = 0, []
        if codigo:
            ns = {}
            try:
                exec(compile(codigo, "<c>", "exec"), ns); f = ns[fn]
                for x, e in casos:
                    try:
                        bien = f(x) == e
                    except Exception:
                        bien = False
                    ok += bien
                    if not bien: fallos.append(x)
            except Exception as e:  # noqa: BLE001
                fallos = [f"no carga: {type(e).__name__}"]
        else:
            fallos = ["sin codigo"]
        tabla[(modelo, nombre)] = (ok, len(casos), seg)
        print(f"{modelo:18} {nombre:14} {ok:2}/{len(casos):<2} {seg:5.0f}s  "
              f"{'APROBADA' if ok == len(casos) else 'fallos: ' + str(fallos)[:70]}", flush=True)
lc.stop_all_except(keep=None)
print("\nRESUMEN (tarea aprobada = todos sus casos)")
for modelo in ("codegemma:7b", "qwen2.5-coder:7b"):
    ap = sum(1 for (m, _), (o, n, _) in tabla.items() if m == modelo and o == n)
    cs = sum(o for (m, _), (o, n, _) in tabla.items() if m == modelo)
    tot = sum(n for (m, _), (o, n, _) in tabla.items() if m == modelo)
    sg = sum(s for (m, _), (o, n, s) in tabla.items() if m == modelo)
    print(f"  {modelo:18} {ap}/7 tareas aprobadas   {cs}/{tot} casos   {sg:.0f}s en total")
