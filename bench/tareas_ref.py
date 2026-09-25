"""Datos de referencia: tareas con verdad escrita a mano. SOLO datos:
importarlo no ejecuta nada."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.especificacion import parsear_formato, generar_valores  # noqa

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
