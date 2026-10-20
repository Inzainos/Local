"""Medición Opción C: verificación por RELACIONES sin oráculo.

Tareas no-formato de la batería + sus propiedades relacionales esperadas.
Si una relación pasa TODOS los valores frontera → tarea VERIFICADA.
Sin modelo en el loop: relaciones se inferen por patrón léxico del enunciado.
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.verificador import (Caso, ejecutar_verificacion, extraer_codigo)  # noqa: E402
from engine.especificacion import parsear_formato, generar_valores               # noqa: E402
from engine.model_lifecycle import ModelLifecycle                      # noqa: E402
import httpx                                                           # noqa: E402

H = "http://127.0.0.1:11434"
FIN = " Devuelve solo la funcion en un bloque de codigo."

# ─── Tareas no-formato + relaciones esperadas ──────────────────────────────
TAREAS = [
    {
        "nombre": "a_segundos",
        "fn": "a_segundos",
        "enunciado": ("Escribe una funcion Python llamada a_segundos(texto: str) -> int "
                      "que convierta duraciones como '2h', '30m', '45s', '1h30m' "
                      "a segundos totales. Devuelve 0 si el texto no es una duracion valida."),
        "relaciones": ["Additive", "ZeroOnInvalid"],
        "casos_base": [("2h", 7200), ("30m", 1800), ("45s", 45), ("1h30m", 5400),
                       ("", 0), ("hola", 0), ("h", 0), ("1x", 0)],
    },
    {
        "nombre": "es_palindromo",
        "fn": "es_palindromo",
        "enunciado": ("Escribe una funcion Python llamada es_palindromo(texto: str) -> bool "
                      "que devuelva True si el texto es palindromo ignorando mayusculas, "
                      "espacios y signos de puntuacion. La cadena vacia devuelve True."),
        "relaciones": ["Idempotent", "ZeroOnInvalid"],  # vacío→True no es "invalid"; ajustar
        "casos_base": [("Anita lava la tina", True), ("", True), ("oso", True),
                       ("A man, a plan, a canal: Panama", True),
                       ("hola", False), ("python", False),
                       ("Anita lava la tuna", False), ("ab", False)],
    },
    {
        "nombre": "es_bisiesto",
        "fn": "es_bisiesto",
        "enunciado": ("Escribe una funcion Python llamada es_bisiesto(anio: int) -> bool "
                      "con la regla gregoriana: divisible entre 4, salvo los divisibles "
                      "entre 100 que no lo sean entre 400."),
        "relaciones": ["Monotonic"],  # no estricta; años bisiestos cada 4
        "casos_base": [(2000, True), (2024, True), (1996, True), (2400, True),
                       (1900, False), (2023, False), (2100, False), (2019, False)],
    },
    {
        "nombre": "a_romano",
        "fn": "a_romano",
        "enunciado": ("Escribe una funcion Python llamada a_romano(n: int) -> str "
                      "que convierta un entero de 1 a 3999 a numeros romanos en "
                      "mayusculas, con notacion sustractiva (4 es IV, 9 es IX)."),
        "relaciones": ["Monotonic"],  # n mayor → romano "más largo" (aprox)
        "casos_base": [(1, "I"), (4, "IV"), (9, "IX"), (14, "XIV"), (40, "XL"),
                       (90, "XC"), (400, "CD"), (1994, "MCMXCIV"), (3999, "MMMCMXCIX")],
    },
    {
        "nombre": "es_ipv4",
        "fn": "es_ipv4",
        "enunciado": ("Escribe una funcion Python llamada es_ipv4(s: str) -> bool "
                      "que devuelva True solo si s es una direccion IPv4 en notacion "
                      "decimal: cuatro numeros de 0 a 255 separados por puntos."),
        "relaciones": ["ZeroOnInvalid"],
        "casos_base": [("192.168.1.1", True), ("0.0.0.0", True),
                       ("255.255.255.255", True), ("8.8.8.8", True),
                       ("10.0.0.256", False), ("1.2.3", False),
                       ("a.b.c.d", False), ("1.2.3.4.5", False)],
    },
]

# ─── Generador de valores frontera por relación ────────────────────────────
def valores_additive(fn, base_casos):
    """Para a_segundos: f('1h30m') == f('1h') + f('30m').
    Solo combina unidades DISTINTAS (h+m, h+s, m+s)."""
    comps = [("1h", 3600), ("30m", 1800), ("45s", 45), ("2h", 7200), ("15m", 900)]
    out = []
    for i in range(len(comps)):
        for j in range(i+1, len(comps)):
            ca, va = comps[i]
            cb, vb = comps[j]
            # Solo combinar si unidades son distintas
            if ca[-1] != cb[-1]:  # 'h' != 'm', 'h' != 's', 'm' != 's'
                out.append((f"{ca}{cb}", va + vb))
    return out

def valores_zero_on_invalid(fn, base_casos):
    """Entradas que el enunciado dice explícitamente que dan 0/False."""
    if fn == "a_segundos":
        invalidos = ["", "hola", "h", "1x", "xyz", ":::"]
    elif fn == "es_palindromo":
        return []  # Idempotent es la relación correcta aquí
    elif fn == "es_ipv4":
        invalidos = ["10.0.0.256", "1.2.3", "a.b.c.d", "1.2.3.4.5", "256.1.1.1", ""]
    elif fn == "es_matricula":
        invalidos = ["", "ABC1234", "AB-123", "ABCD-1234", "abc-1234"]
    elif fn == "es_bisiesto":
        return []
    else:
        invalidos = []
    return [(x, 0) for x in invalidos]

def valores_idempotent(fn, base_casos):
    """Para validadores booleanos: f(x) == True → f(limpiar(x)) == True.
    Idempotencia real en validadores: f(x) == f(normalizar(x)).
    Simplificación medible: entradas válidas devuelven True consistentemente (ya en base).
    Usamos: f(x) == True implica que x normalizado también da True."""
    validos = [x for x, e in base_casos if e is True]
    return [(x, True) for x in validos]

def valores_monotonic(fn, base_casos):
    """Orden: para a_segundos, más tiempo → más segundos."""
    out = []
    if fn == "a_segundos":
        orden = [("1s", 1), ("30s", 30), ("1m", 60), ("2m", 120), ("1h", 3600), ("2h", 7200)]
        for i in range(len(orden)):
            for j in range(i+1, len(orden)):
                ca, va = orden[i]
                cb, vb = orden[j]
                out.append((f"{ca}<{cb}", va < vb))
    # es_bisiesto, a_romano: no hay orden lineal simple medible sin decodificador
    return out

GENERADORES = {
    "Additive": valores_additive,
    "ZeroOnInvalid": valores_zero_on_invalid,
    "Idempotent": valores_idempotent,
    "Monotonic": valores_monotonic,
}

def generar_casos_relacion(fn, relacion, base_casos):
    gen = GENERADORES[relacion]
    return [Caso(f"{fn}({x!r})", repr(e)) for x, e in gen(fn, base_casos)]

# ─── Medición ────────────────────────────────────────────────────────────────
lc = ModelLifecycle()
lc.ensure_exclusive("codegemma:7b", num_ctx=8192)

def generar(modelo, prompt):
    with httpx.Client(timeout=900) as c:
        r = c.post(f"{H}/api/generate", json={
            "model": modelo, "prompt": prompt, "stream": False, "keep_alive": "5m",
            "options": {"temperature": 0.0, "num_ctx": 8192, "num_predict": 1200, "seed": 7}}).json()
    return r.get("response", "")

print("=== OPCIÓN C: verificación por relaciones (codegemma, temp 0) ===\n")
resultados = {}

for t in TAREAS:
    nombre, fn, enunciado, rels, base = t["nombre"], t["fn"], t["enunciado"], t["relaciones"], t["casos_base"]
    prompt = enunciado + FIN
    codigo = extraer_codigo(generar("codegemma:7b", prompt), fn)
    print(f"\n--- {nombre} ---")
    if not codigo:
        print("  sin código")
        resultados[nombre] = {"codigo": False}
        continue
    
    # Verificación base (casos de verdad)
    casos_base = [Caso(f"{fn}({x!r})", repr(e)) for x, e in base]
    v_base = ejecutar_verificacion(codigo, casos_base)
    print(f"  base: {v_base.aciertos}/{v_base.total} {'✅' if v_base.aciertos==v_base.total else '❌'}")
    
    # Verificación por relaciones
    rel_ok = True
    for rel in rels:
        casos_rel = generar_casos_relacion(fn, rel, base)
        v_rel = ejecutar_verificacion(codigo, casos_rel)
        ok = v_rel.total > 0 and v_rel.aciertos == v_rel.total
        rel_ok = rel_ok and ok
        print(f"  {rel}: {v_rel.aciertos}/{v_rel.total} {'✅' if ok else '❌'} ({len(casos_rel)} casos)")
    
    resultados[nombre] = {"base": v_base.aciertos==v_base.total, "relaciones": rel_ok, "codigo": True}

lc.stop_all_except(keep=None)

# ─── Resumen ─────────────────────────────────────────────────────────────────
print("\n=== RESUMEN OPCIÓN C ===")
for nombre, r in resultados.items():
    if not r.get("codigo"):
        estado = "SIN CÓDIGO"
    elif r["base"] and r["relaciones"]:
        estado = "✅ VERIFICADO (base + relaciones)"
    elif r["base"]:
        estado = "✅ base OK, ❌ relaciones"
    else:
        estado = "❌ base falla"
    print(f"  {nombre:16} {estado}")
