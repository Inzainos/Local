"""
Static UVG-125 Node Matrix — loaded into RAM at import time.

The 125 nodes de la malla N-Body usan coordenadas geograficas REALES,
tomadas de la unica fuente de verdad topologica: SEED_NODOS
(infrastructure/database/seed_nodos.py).

CAMBIO v2.5.2 (10-13 ago 2026) — FIX CRITICO DE LOCALIZACION:
Version anterior generaba 102 de los 125 nodos con coordenadas
matematicas ficticias (lat = sin(i/PHI)*90, lon = cos(i/PHI)*180),
sin relacion alguna con geografia real. Confirmado en produccion:
el sismo real M7.4 de Choco, Colombia (2026-08-10) fue asignado
al nodo "Chiapas Subduccion" (Mexico, ~1700km de error) en vez del
nodo real mas cercano ("Colombia-Ecuador", ~350km), porque ese nodo
(id=30) no tenia coordenadas reales en el motor de calculo.

Este archivo ahora importa SEED_NODOS directamente — una sola fuente
de verdad para topologia, compartida entre el motor de calculo y los
reportes. Ya no hay generacion procedural de coordenadas fantasma.

Layout (heredado de SEED_NODOS, ver seed_nodos.py):
  - Nodes 1-50: Real (major seismic zones, volcanic centers, subduction zones)
  - Nodes 51-100: Ghost (shadow nodes inferred from geodynamic gaps)
  - Nodes 101-125: Geobattery (electrochemical accumulation zones)
  - Node 0: Observation point (Tlaxcala — asynchronous, does not affect Euler sum)
"""

import numpy as np

from sentinel_omega.infrastructure.database.seed_nodos import SEED_NODOS

PHI = (1 + np.sqrt(5)) / 2  # Se conserva por compatibilidad con otros modulos que la importen de aqui.
RADIO_TERRESTRE_KM = 6371.0

NODO_OBSERVACION = {
    "id": 0,
    "tipo": "observacion",
    "lat": 19.3182,
    "lon": -98.2375,
    "name": "TLAXMASTER",
    "region": "Mexico",
    "conductividad": None,
}


def _generar_matriz_125() -> list:
    """Construye la matriz 125+1 en RAM a partir de SEED_NODOS (coordenadas reales).

    Ya no hay rama procedural con formula aurea. Cada uno de los 125 nodos
    usa exactamente la misma lat/lon/tipo/region que ve el pipeline de
    reportes (estado/), garantizando que el motor de calculo y los reportes
    hablen siempre de la misma geografia para el mismo id de nodo.
    """
    matriz = [NODO_OBSERVACION]

    seed_por_id = {n["node_id"]: n for n in SEED_NODOS}

    if len(seed_por_id) != 125:
        raise ValueError(
            f"SEED_NODOS debe tener exactamente 125 nodos, encontrados: {len(seed_por_id)}"
        )

    for i in range(1, 126):
        if i not in seed_por_id:
            raise KeyError(f"Falta node_id={i} en SEED_NODOS — matriz de topologia incompleta.")
        nodo = seed_por_id[i]
        matriz.append({
            "id": i,
            "tipo": nodo["tipo"],
            "lat": nodo["lat"],
            "lon": nodo["lon"],
            "name": nodo["nombre"],
            "region": nodo.get("region", ""),
            "conductividad": nodo.get("conductividad"),
        })

    return matriz


MATRIZ_UVG_125 = _generar_matriz_125()

NODOS_POR_ID = {n["id"]: n for n in MATRIZ_UVG_125}


def nodo_mas_cercano(lat: float, lon: float) -> dict:
    """Find the nearest UVG node to given coordinates. O(n) in-memory lookup.

    NOTA: sigue usando distancia euclidiana en grados (no haversine) por
    consistencia con el comportamiento previo del sistema en produccion;
    no se cambia la metrica de distancia en este parche, solo la fuente
    de coordenadas. Si se requiere precisión geodésica real (relevante
    cerca de los polos o para distancias largas), evaluar migrar a
    haversine en un parche separado.
    """
    return min(
        MATRIZ_UVG_125,
        key=lambda n: (lat - n["lat"]) ** 2 + (lon - n["lon"]) ** 2,
    )
