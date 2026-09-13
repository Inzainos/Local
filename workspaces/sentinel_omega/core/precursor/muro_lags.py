"""
Muro de Lags — convergencia temporal de firmas matcheadas.

Extensión del Muro de los 5 Eventos al eje del TIEMPO: cada firma matcheada
en vivo trae su propia ventana típica de presentación (su lag aprendido).
Si varias firmas independientes convergen en la misma ventana de fechas,
el muro se activa: no solo "hay señal", sino "varias memorias distintas
apuntan a las MISMAS fechas".

Ventana por match: [0.5 x lag, 1.5 x lag] días desde ahora (la mitad y el
150% de su tiempo típico). Breach cuando >= 3 firmas se traslapan.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

MIN_CONVERGENCIA = 3


def evaluar_muro_lags(
    matches: List[Dict[str, Any]],
    ahora: Optional[datetime] = None,
    min_convergencia: int = MIN_CONVERGENCIA,
) -> Dict[str, Any]:
    """Evaluate temporal convergence of matched signatures' expected windows.

    Each match needs "ventana_tipica_dias" (its firma's learned lag).
    Returns the tightest overlapping window shared by the most firmas.
    """
    now = ahora or datetime.now(timezone.utc)

    intervalos = []
    for m in matches:
        lag = m.get("ventana_tipica_dias")
        if not lag or lag <= 0:
            continue
        intervalos.append({
            "ini": 0.5 * lag,
            "fin": 1.5 * lag,
            "firma_id": m.get("firma_id"),
            "event_class": m.get("event_class"),
            "similitud": m.get("similitud", 0.0),
        })

    base = {
        "activo": False,
        "firmas_convergentes": 0,
        "firmas_con_ventana": len(intervalos),
    }
    if len(intervalos) < min_convergencia:
        return base

    # Sweep: the day-offset covered by the most windows simultaneously
    puntos = sorted(
        {i["ini"] for i in intervalos} | {i["fin"] for i in intervalos}
    )
    mejor_punto, mejor_n = None, 0
    for p in puntos:
        n = sum(1 for i in intervalos if i["ini"] <= p <= i["fin"])
        if n > mejor_n:
            mejor_n, mejor_punto = n, p

    if mejor_n < min_convergencia:
        base["firmas_convergentes"] = mejor_n
        return base

    dentro = [i for i in intervalos if i["ini"] <= mejor_punto <= i["fin"]]
    ini = max(i["ini"] for i in dentro)
    fin = min(i["fin"] for i in dentro)

    return {
        "activo": True,
        "firmas_convergentes": mejor_n,
        "firmas_con_ventana": len(intervalos),
        "ventana_dias": [round(ini, 1), round(fin, 1)],
        "fecha_inicio": (now + timedelta(days=ini)).strftime("%Y-%m-%d"),
        "fecha_fin": (now + timedelta(days=fin)).strftime("%Y-%m-%d"),
        "clases": sorted({i["event_class"] for i in dentro if i["event_class"]}),
        "similitud_max": max(i["similitud"] for i in dentro),
    }


def format_muro_lags(resultado: Dict[str, Any]) -> str:
    if not resultado.get("activo"):
        return (
            f"Muro de Lags: sin convergencia "
            f"({resultado.get('firmas_convergentes', 0)} firmas)"
        )
    return (
        f"🕐 MURO DE LAGS ACTIVO: {resultado['firmas_convergentes']} firmas "
        f"convergen en la ventana {resultado['fecha_inicio']} → "
        f"{resultado['fecha_fin']} "
        f"({resultado['ventana_dias'][0]}-{resultado['ventana_dias'][1]} días) "
        f"| clases: {', '.join(resultado['clases'])}"
    )
