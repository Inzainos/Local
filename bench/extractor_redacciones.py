"""¿La especificación sobrevive a otra REDACCIÓN del mismo enunciado?

Origen (2026-09-25, en vivo por Telegram): «que acepte identificador numerico,
DOS PUNTOS y un secreto…» en vez de «que devuelva True solo si…». El extractor
dio al identificador longitud máxima 1, la defensa lo dejó pasar («un
secreto» contaba como 1) y el verificador rechazó 4 rondas un código correcto.

Por cada redacción: extractor real (qwen2.5-coder:7b, temperatura 0, como en
agents/optimizer.py), y los casos se ejecutan contra un código CORRECTO (debe
pasar todos: si no, rechazo falso) y contra códigos ROTOS (deben fallar
alguno: si no, aprobación falsa). Las tareas que no son de formato deben
decir «no aplica». Se ejecuta al correrlo: no lo importes.
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.especificacion import extraer_formato, casos_desde_formato  # noqa: E402
from engine.model_lifecycle import ModelLifecycle                        # noqa: E402
from engine.tool_agent import run_with_tools                             # noqa: E402
from engine.verificador import ejecutar_verificacion                     # noqa: E402
from tareas_ref import TAREAS                                            # noqa: E402

MODELO = "qwen2.5-coder:7b"
F = "Escribe una funcion Python llamada "
TOKEN_OK = ('import re\ndef validar_token_telegram(token):\n'
            '    return bool(re.fullmatch(r"\\d+:[A-Za-z0-9_-]{35}", token or ""))\n')
TOKEN_ROTOS = [
    'def validar_token_telegram(token):\n    return len(token) == 39 and token.isalnum()\n',
    'import re\ndef validar_token_telegram(token):\n'
    '    return bool(re.fullmatch(r"\\d+:[A-Za-z0-9_-]{30,40}", token))\n',
    'import re\ndef validar_token_telegram(token):\n'
    '    return bool(re.match(r"\\d+:[A-Za-z0-9]{35}", token))\n',
]
MAT_OK = ('import re\ndef es_matricula(s):\n'
          '    return bool(re.fullmatch(r"[A-Z]{3}-[0-9]{4}", s or ""))\n')
MAT_ROTOS = [
    'def es_matricula(s):\n    return len(s) == 8 and s[0:3].isupper() and s[3] == "-" and s[4:].isdigit()\n',
    'import re\ndef es_matricula(s):\n    return bool(re.match(r"[A-Z]{3}-\\d{4}", s))\n',
]
FORMATO = [
    ("token/bateria", F + "validar_token_telegram(token: str) -> bool que devuelva True solo si "
     "el token tiene el formato valido de la API de Telegram: identificador numerico, DOS PUNTOS, "
     "y un secreto de EXACTAMENTE 35 caracteres del alfabeto [A-Za-z0-9_-].", TOKEN_OK, TOKEN_ROTOS),
    ("token/vivo", F + "validar_token_telegram(token: str) -> bool que acepte identificador "
     "numerico, DOS PUNTOS y un secreto de EXACTAMENTE 35 caracteres del alfabeto [A-Za-z0-9_-]",
     TOKEN_OK, TOKEN_ROTOS),
    ("token/voz", F + "validar_token_telegram(token: str) -> bool, el token es un numero, luego "
     "dos puntos y luego un secreto de 35 caracteres que pueden ser letras, digitos, guion bajo o "
     "guion", TOKEN_OK, TOKEN_ROTOS),
    ("matricula/bateria", F + "es_matricula(s: str) -> bool que devuelva True solo si s tiene tres "
     "letras mayusculas, un guion y cuatro digitos, por ejemplo ABC-1234.", MAT_OK, MAT_ROTOS),
    ("matricula/vivo", F + "es_matricula(s: str) -> bool que acepte tres letras mayusculas, un "
     "guion y cuatro digitos", MAT_OK, MAT_ROTOS),
]
NO_FORMATO = [(t[0], t[2]) for t in TAREAS if t[0] not in ("validar_token", "es_matricula")]

lc = ModelLifecycle()
lc.ensure_exclusive(MODELO, num_ctx=4096)
llamadas = []


def invocar(prompt, esquema):
    llamadas.append(prompt)
    return run_with_tools(model=MODELO, user_prompt=prompt,
                          system_prompt="Describes formatos. Devuelves solo JSON. No resuelves nada.",
                          ollama_host="http://127.0.0.1:11434", tools_schema=None,
                          tool_impls=None, max_iterations=1, num_ctx=4096,
                          format_schema=esquema, temperature=0.0)


malos = 0
for nombre, enunciado, ok, rotos in FORMATO:
    llamadas.clear()
    t0 = time.time()
    fmt, motivo = extraer_formato(enunciado, invocar)
    dt = time.time() - t0
    if fmt is None:
        print(f"{nombre:18s} SIN ESPECIFICACIÓN ({len(llamadas)} llamadas, {dt:.0f}s): {motivo}")
        continue
    casos = casos_desde_formato(fmt)
    v = ejecutar_verificacion(ok, casos)
    pasan_rotos = [i for i, r in enumerate(rotos)
                   if (lambda w: w.aciertos == w.total)(ejecutar_verificacion(r, casos))]
    falso = v.aciertos != v.total or pasan_rotos
    malos += bool(falso)
    print(f"{nombre:18s} {fmt.regex().pattern:45s} {len(llamadas)} llamadas {dt:3.0f}s | correcto "
          f"{v.aciertos}/{v.total} | rotos aprobados {pasan_rotos} {'<-- MAL' if falso else ''}")

for nombre, enunciado in NO_FORMATO:
    llamadas.clear()
    fmt, motivo = extraer_formato(enunciado, invocar)
    malos += fmt is not None
    print(f"{nombre:18s} {'no aplica' if fmt is None else 'APLICA: ' + fmt.regex().pattern:45s} "
          f"{len(llamadas)} llamadas | {motivo[:70]}")
lc.stop_model(MODELO)
print("\nresultados malos:", malos)
