"""¿Qué modelo EXTRAE bien la especificación? Misma vara que antes: ejecutar.

Dos enunciados:
  token      validador de formato -> debe extraer y los casos deben separar
  segundos   NO es un formato     -> debe decir aplica=false
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine.especificacion import extraer_formato, casos_desde_formato  # noqa
from engine.model_lifecycle import ModelLifecycle                        # noqa
from engine.tool_agent import run_with_tools                             # noqa
from engine.verificador import ejecutar_verificacion                     # noqa
from comparar_derivadores import ENUNCIADO, CORRECTO, ROTO_REAL, CONSTANTE        # noqa

SEGUNDOS = ("Escribe una funcion Python llamada a_segundos(texto: str) -> int que "
            "convierta duraciones como '2h', '30m', '45s', '1h30m' a segundos "
            "totales. Devuelve 0 si el texto no es una duracion valida.")
SISTEMA = "Describes formatos. Devuelves solo JSON. No resuelves nada."
lc = ModelLifecycle()
filas = []
for m in ("nemotron-mini", "llama3.2:3b", "gemma3:4b", "mistral:7b", "qwen2.5-coder:7b"):
    lc.ensure_exclusive(m, num_ctx=4096)
    inv = lambda p, esq: run_with_tools(model=m, system_prompt=SISTEMA, user_prompt=p,
                                        ollama_host="http://127.0.0.1:11434",
                                        tools_schema=None, tool_impls=None,
                                        max_iterations=1, num_ctx=4096,
                                        format_schema=esq)
    crudo = {}
    def inv_espia(p, esq, _inv=inv):
        r = _inv(p, esq); crudo["t"] = r; return r
    fmt, err = extraer_formato(ENUNCIADO, inv_espia)
    if fmt:
        partes = " ".join(f"[{p.texto}]" if p.tipo == "separador"
                          else f"{p.alfabeto[:3]}..{{{p.minimo},{p.maximo or '∞'}}}"
                          for p in fmt.partes)
        cs = casos_desde_formato(fmt)
        r = {n: ejecutar_verificacion(c, cs) for n, c in
             (("bueno", CORRECTO), ("roto", ROTO_REAL), ("const", CONSTANTE))}
        tok = (f"OK {partes} | bueno={r['bueno'].puntuacion_util} "
               f"roto={r['roto'].puntuacion_util} const={r['const'].puntuacion_util}")
    else:
        tok = f"RECHAZADO: {err[:70]}"
    fmt2, err2 = extraer_formato(SEGUNDOS, inv)
    seg = "dijo NO aplica (bien)" if fmt2 is None and "no es una validación" in err2 \
        else (f"rechazado por defensa: {err2[:50]}" if fmt2 is None
              else "EXTRAJO UN FORMATO (mal)")
    lc.stop_model(m)
    print(f"\n{m}\n  token   : {tok}\n  segundos: {seg}", flush=True)
    print(f"  crudo   : {crudo.get('t','')[:300]}", flush=True)
