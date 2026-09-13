"""Decide la accion segun la politica elegida por el usuario:
cuarentena SIEMPRE para cualquier hallazgo, borrado automatico SOLO si:
  VT positives >= umbral Y VT total >= umbral Y OTX confirma hit.
Nunca se borra nada sin pasar primero por cuarentena (con su forense
guardado), asi que 'auto_delete' es en realidad 'cuarentena + borrado
inmediato', no un borrado ciego."""

ALERT_ONLY = "alert_only"
QUARANTINE = "quarantine"
AUTO_DELETE = "auto_delete"


def decide(cfg, intel: dict) -> str:
    """intel: {"vt": {"positives":.., "total":..} | None,
               "otx": {"hit": bool} | None,
               "ip_rep": {"abuse_score":..} | None}"""
    vt = intel.get("vt")
    otx = intel.get("otx")

    min_pos = cfg.get("policy", "auto_delete_min_vt_positives", default=15)
    min_total = cfg.get("policy", "auto_delete_min_vt_total", default=70)
    require_otx = cfg.get("policy", "require_otx_confirmation", default=True)

    if vt and vt.get("positives", 0) >= min_pos and vt.get("total", 0) >= min_total:
        if not require_otx:
            return AUTO_DELETE
        if otx and otx.get("hit"):
            return AUTO_DELETE

    # Cualquier senal de intel positiva (aunque no llegue al umbral de
    # borrado) o heuristica local ya amerita cuarentena, nunca solo alerta.
    return QUARANTINE
