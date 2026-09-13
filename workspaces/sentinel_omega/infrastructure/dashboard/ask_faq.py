"""FAQ matcher: preguntas SOLO sobre Sentinel Omega. Nunca inventa cifras vivas."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Tuple

GLOSSARY: List[Tuple[Tuple[str, ...], str]] = [
    (("fantasma", "indice fantasma", "indice de riesgo"),
     "Fantasma es el indice de riesgo cosmico que arma Sentinel a partir de datos reales "
     "(campo magnetico Bz, viento solar, resonancia Schumann, Kp, LOD). "
     "NO es una prediccion de terremoto. Escala: LOW menor a 5 (calma), MODERATE 5-15 "
     "(atencion), HIGH 15-30 (avisar), CRITICAL 30 o mas (protocolo). "
     "La cifra viva se lee de TBL_PRECURSORES_COSMICOS, nunca se inventa."),
    (("muro", "muro 5", "cinco eventos", "breach"),
     "El Muro de los 5 Eventos cruza cinco 'paredes' de senales: geofisico, atmosferico, "
     "oceanico, solar y financiero. Se considera BREACH (rotura) cuando hay 3 o mas paredes "
     "activas a la vez. Eso pide atencion humana; no es una alarma de compra ni de huida."),
    (("ciclo", "ciclos", "orquestador"),
     "Un ciclo es una pasada del orquestador: baja datos, calcula Fantasma, evalua el Muro "
     "y registra el resultado en TBL_CICLOS. Si el ultimo ciclo tiene mas de ~10 minutos, "
     "el tablero avisa que no hay lectura reciente."),
    (("sismo", "sismos", "m4.5", "4.5", "magnitud"),
     "Sentinel MIDE desde magnitud 3.3 (piso del backcast) pero ALERTA solo desde M4.5. "
     "Por eso el tablero lista sismos >= 4.5 del catalogo USGS (TBL_HISTORICO_SISMICO). "
     "M4.5 no es un numero magico de prediccion: es el umbral operativo del Padre."),
    (("nodo", "nodos", "topologia", "ghost", "fantasma nodo", "geobattery", "real"),
     "Hay 125 nodos de topologia (teoria UVG-125): 50 reales, 50 ghost (sombra) y 25 "
     "geobateria. Cada uno tiene lat/lon. Un nodo es un punto de observacion/carga, "
     "no una estacion sismica certificada. Tlaxcala es el nodo de observacion de Sentinel."),
    (("moderate", "moderado", "nivel de riesgo", "low", "high", "critical"),
     "Los niveles salen del Fantasma: LOW <5 (todo en calma, no hay que llamar a nadie), "
     "MODERATE 5-15 (el sistema esta inquieto, revisar Muro y sismos), HIGH 15-30 "
     "(avisar a quien corresponda), CRITICAL >=30 (protocolo). No significa que 'va a temblar'."),
    (("cimatica", "cymatica", "patron"),
     "Cimatica es la memoria de formas de vibracion/estado que los bots ya vieron. "
     "Ambito 'general' = el sistema entero; ambito 'nodo' = un punto. Un patron que se "
     "repite y despues coincidio con un evento es una pista, no una profecia."),
    (("schumann", "7.83", "resonancia"),
     "La resonancia Schumann es el 'latido' electromagnetico de la Tierra, cerca de 7.83 Hz. "
     "Beta-1 la usa como referencia. Si Schumann se altera JUNTO con otras senales, "
     "el sistema marca precursor. Una desviacion sola no basta."),
    (("padre", "consenso", "bot"),
     "Hay varios modelos (alfa1, alfa2, beta1, beta2, delta, omega, jupiter) y el Padre "
     "valida en cruz. El Padre es quien puede avisar. Cada bot tiene peso y asertividad "
     "viva (aciertos contra fallos del Juez, fase viva)."),
    (("juez", "asertividad", "acierto", "fallo", "viva"),
     "El Juez (TBL_JUEZ_AUDITORIA) compara prediccion vs realidad. La vara canonica es la "
     "vista viva_real (solo fase='viva'). Asertividad viva individual = aciertos/(aciertos+fallos) "
     "por bot en TBL_PESOS_BOTS. La historica de entrenamiento esta en tbl_sesgo_aprendizaje."),
    (("sesgo", "insample", "causal", "beta2"),
     "Sesgo = que tan bien se ve un bot DENTRO del entrenamiento (insample) vs FUERA "
     "(causal). Si insample es alto y causal cae, el bot 'se ve bien en el examen' pero "
     "empeora en vivo. Eso hay que leerlo, no esconderlo."),
    (("omega", "snt", "sateliz"),
     "SNT (Shadow Node Theory) es el marco matematico R(t)=a·t^b, no el proposito del "
     "sistema. Streamlit tenia una pestana SNT con curvas DEMO; este tablero no inventa "
     "esas curvas. Omega guarda memoria de correlaciones (luna, Schumann, mercado)."),
    (("lag", "anticipacion"),
     "Los lags dicen, en horas, cuanto ANTES se vio un patron respecto de un evento "
     "etiquetado. Salen de tbl_lag_anticipacion y tbl_factores_lag. Son estadistica "
     "historica, no un reloj de cuenta regresiva."),
    (("correlacion", "fuerza", "patron"),
     "tbl_correlaciones_padre y _omega cuentan cuantas veces un patron de senales "
     "coincidio con una clase de evento (fuerza entre 0 y 1). Rojo/alto = se vio seguido; "
     "azul/bajo = raro. No es causalidad."),
    (("predice", "prediccion", "va a temblar", "loteria", "comprar", "invertir"),
     "Sentinel Omega vigila PRECURSORES de eventos naturales con datos reales. "
     "No es un juguete de prediccion, no recomienda comprar ni vender, y no 'colapsa "
     "la funcion de onda a tu favor'. Si alguien pide consejo de apuesta, la respuesta "
     "es no."),
]

def _fold(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def answer_question(question: str, live: Dict[str, Any]) -> Dict[str, Any]:
    q = (question or "").strip()
    if not q:
        return {"answer": "Escribe una pregunta sobre Sentinel Omega (Fantasma, Muro, nodos, sismos…).", "citations": []}
    folded = _fold(q)
    hits: List[str] = []
    texts: List[str] = []
    for keys, text in GLOSSARY:
        if any(_fold(k) in folded for k in keys):
            texts.append(text)
            hits.extend(keys[:1])
    live_bits = _live_sentence(live)
    if not texts:
        texts.append(
            "Solo puedo hablar del sistema Sentinel Omega (Fantasma, Muro, ciclos, nodos, "
            "sismos, cimatica, bots, Juez). Reformula con una de esas palabras."
        )
    texts.append(live_bits)
    return {"answer": " ".join(texts), "citations": hits + ["overview"]}


def _live_sentence(live: Dict[str, Any]) -> str:
    f = live.get("fantasma") or {}
    m = live.get("muro") or {}
    c = live.get("counts") or {}
    val = f.get("value")
    nivel = f.get("nivel_riesgo") or "—"
    walls = m.get("walls_active")
    breach = m.get("muro_breach")
    sismos = c.get("sismos_m45")
    nodos = c.get("nodos")
    parts = ["Cifras vivas de /api/overview (SQLite RO, no inventadas):"]
    parts.append(f"Fantasma={val if val is not None else 'sin dato'} ({nivel}).")
    parts.append(f"Muro={walls if walls is not None else '—'} / 5 paredes" + (" con BREACH." if breach else " sin breach."))
    parts.append(f"Nodos={nodos if nodos is not None else '—'}; sismos >=4.5 en catalogo={sismos if sismos is not None else '—'}.")
    return " ".join(parts)
