"""
Sentinel Omega — AlertService unificado
Centraliza reportes, alertas y mensajes de Telegram/Correo/Log.
Antes: formatos dispersos en telegram.py, correo.py, muro_*.py, risk_calculator.py
Ahora: unico punto con templates versionables y despacho multi-canal.

Telegram (canal Padre / consenso):
  AlertService.dispatch → ConsensoVigilante
    - digest horario SIEMPRE (TG_DIGEST_MINUTES, default 60)
    - envío inmediato SOLO si is_unprecedented (sin registro previo)
  Correo y log no pasan por el vigilante.
"""
from __future__ import annotations
import logging, os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any
from pathlib import Path
logger = logging.getLogger(__name__)
class Severity(str, Enum):
    ROJO = "rojo"
    AMARILLO = "amarillo"
    VERDE = "verde"
    AZUL = "azul"
SEVERITY_EMOJI = {Severity.ROJO: "🔴", Severity.AMARILLO: "🟠", Severity.VERDE: "🟢", Severity.AZUL: "🔵"}
@dataclass
class FormattedMessage:
    html: str
    markdown: str
    plain: str
    subject: str
    severity: Severity
    alert_type: str
def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
def _window_str(hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%d/%m %H:%M UTC")
def _strip_tags(html: str) -> str:
    return (
        html.replace("<b>", "").replace("</b>", "")
        .replace("<i>", "").replace("</i>", "")
        .replace("<code>", "").replace("</code>", "")
        .replace("<br>", "\n").replace("<br/>", "\n")
    )
class AlertTemplates:
    @staticmethod
    def centinela_critico(risk: float, bz: float, wind: float, schumann: Optional[float] = None, severity: Severity = Severity.ROJO) -> FormattedMessage:
        subj = f"[SENTINEL] ALERTA CRITICA — Fantasma {risk:.2f}"
        extra = f"\n🌐 Schumann: {schumann:.2f} Hz — latido electromagnético de la Tierra." if schumann else ""
        html = (
            f"🔴 <b>ALERTA CRITICA</b>\n\n"
            f"⚠️ Fantasma: <b>{risk:.2f}</b> — índice 0–10 de estrés geofísico "
            f"(Bz² + viento solar + Schumann). No es un pronóstico de sismo ni de epicentro.\n"
            f"🧲 Bz: {bz:.1f} nT — componente norte-sur del campo; negativo profundo = grieta en el escudo.\n"
            f"💨 Viento: {wind:.0f} km/s — flujo solar sobre la magnetosfera.{extra}\n"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**ALERTA CRITICA**\n\nFantasma: **{risk:.2f}** (estrés geofísico, no pronóstico)\nBz: {bz:.1f} nT | Viento: {wind:.0f} km/s{extra}"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=severity, alert_type="CRITICO")
    @staticmethod
    def centinela_grieta(bz: float) -> FormattedMessage:
        subj = f"[SENTINEL] GRIETA — Bz {bz:.1f} nT"
        html = (
            f"🛡️ <b>FALLO DE ESCUDO (GRIETA)</b>\n\n"
            f"Bz colapsado: <b>{bz:.1f} nT</b>\n"
            f"Qué significa: el campo magnético terrestre se abrió hacia el sur; "
            f"puede entrar energía solar. No implica un sismo por sí solo.\n"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**FALLO DE ESCUDO (GRIETA)**\n\nBz colapsado: **{bz:.1f} nT**"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=Severity.ROJO, alert_type="GRIETA")
    @staticmethod
    def centinela_tormenta(wind: float) -> FormattedMessage:
        subj = f"[SENTINEL] TORMENTA SOLAR — Viento {wind:.0f} km/s"
        html = (
            f"🌪️ <b>TORMENTA SOLAR</b>\n\n"
            f"Viento: <b>{wind:.0f} km/s</b> (típico ~400; tormenta ≥600).\n"
            f"Qué significa: presión sobre la magnetosfera. Puede subir Kp y Fantasma; "
            f"no es un aviso de sismo ni de epicentro.\n"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**TORMENTA SOLAR**\n\nViento: **{wind:.0f} km/s**"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=Severity.AMARILLO, alert_type="TORMENTA")
    @staticmethod
    def centinela_advertencia(risk: float, bz: float, wind: float) -> FormattedMessage:
        subj = f"[SENTINEL] Actividad elevada — Fantasma {risk:.2f}"
        html = (
            f"🟠 <b>ACTIVIDAD ELEVADA</b>\n\n"
            f"Fantasma: {risk:.2f} — por encima del umbral de vigilancia, aún no crítico.\n"
            f"Bz: {bz:.1f} nT | Viento: {wind:.0f} km/s\n"
            f"Qué significa: el índice subió; entra al reporte horario del Padre, "
            f"no es un page inmediato salvo que sea un patrón sin precedentes.\n"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**ACTIVIDAD ELEVADA**\n\nFantasma: {risk:.2f}"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=Severity.AMARILLO, alert_type="ADVERTENCIA")
    @staticmethod
    def precursor(
        precursor_type: str,
        display_name: str,
        value: float,
        details: str,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        lugar: Optional[str] = None,
        lag_horas: Optional[float] = None,
        lag_max_h: Optional[float] = None,
        id_nodo=None,
        nodo_nombre: Optional[str] = None,
        region: Optional[str] = None,
        enriched: Optional[Dict] = None,
    ) -> FormattedMessage:
        subj = "[SENTINEL] PRECURSOR %s — %.0f%%" % (display_name, value * 100)
        en: Dict = dict(enriched or {})
        if lugar and not en.get("lugar"):
            en["lugar"] = lugar
        if lat is not None:
            en.setdefault("lat", lat)
        if lon is not None:
            en.setdefault("lon", lon)
        if id_nodo is not None:
            en.setdefault("id_nodo", id_nodo)
        if nodo_nombre:
            en.setdefault("nodo_nombre", nodo_nombre)
        if region:
            en.setdefault("region", region)
        if lag_horas is not None:
            en.setdefault("lag_horas", lag_horas)
        if lag_max_h is not None:
            en.setdefault("lag_max_h", lag_max_h)
        try:
            from sentinel_omega.infrastructure.messaging.alert_enrichment import (
                location_block, format_lag_line,
            )
            loc = location_block(en)
            lag_line = format_lag_line(en.get("lag_horas"), en.get("lag_max_h"))
        except Exception:
            loc = ""
            if en.get("lugar"):
                loc += "📍 <b>Ubicación:</b> " + str(en["lugar"])
            if en.get("lat") is not None and en.get("lon") is not None:
                loc += (
                    chr(10) + "🌐 <b>Coords:</b> <code>%.2f, %.2f</code>"
                    % (float(en["lat"]), float(en["lon"]))
                )
            lag_line = ""
            if en.get("lag_horas"):
                lag_line = (
                    "⏱ <b>Lag / ventana:</b> ~%.0f h → %s"
                    % (float(en["lag_horas"]), _window_str(int(float(en["lag_horas"]))))
                )
        if not lag_line:
            lag_line = (
                "⏱ <b>Ventanas de vigilancia:</b> 72h→%s · 48h→%s · 24h→%s"
                % (_window_str(72), _window_str(48), _window_str(24))
            )
        det = (details or "").strip()
        if en.get("detalle") and str(en["detalle"]) not in det:
            det = (str(en["detalle"]) + ((chr(10) + det) if det else "")).strip()
        parts = [
            "<b>SENTINEL OMEGA — PRECURSOR</b>",
            "",
            "<b>Tipo:</b> " + str(display_name),
            ("<b>Confianza:</b> <code>%.0f%%</code> — parecido a firmas ya vistas; "
             "no es probabilidad de sismo ni de epicentro.") % (value * 100),
        ]
        if loc:
            parts.append(loc)
        parts.append(lag_line)
        parts.append("📋 <b>Detalle:</b> " + (det or "sin métricas extra"))
        parts.append("")
        parts.append("<i>Entra al reporte horario del Padre; solo pagina si es un patrón sin registro previo.</i>")
        parts.append("<i>%s</i>" % _now_utc_str())
        html = chr(10).join(parts)
        md = "**SENTINEL OMEGA — PRECURSOR %s**%sConf: **%.0f%%**%s%s" % (
            display_name, chr(10), value * 100, chr(10), det)
        sev = Severity.ROJO if value >= 0.75 else Severity.AMARILLO if value >= 0.55 else Severity.VERDE
        return FormattedMessage(
            html=html, markdown=md, plain=_strip_tags(html), subject=subj,
            severity=sev, alert_type="PRECURSOR_%s" % precursor_type.upper(),
        )

    @staticmethod
    def consenso(
layer: str, signal_type: str, confidence: float, agents_n: int, dual_ask: Optional[Dict]=None, omega_voto: Optional[Dict]=None) -> FormattedMessage:
        sev = Severity.ROJO if signal_type.lower()=="alert" else Severity.AMARILLO if signal_type.lower()=="watch" else Severity.VERDE
        subj = f"[SENTINEL] {layer.upper()} CONSENSO — {signal_type} {confidence:.0%}"
        lines = [
            f"<b>SENTINEL OMEGA — {layer.upper()} CONSENSUS</b>\n",
            f"Final: <code>{signal_type}</code> ({confidence:.0%}) — voto cruzado de los agentes; no es un tip ni un pronóstico.",
            f"Agents: <code>{agents_n}</code>",
        ]
        if omega_voto: lines.append(f"Ω Omega: <code>{omega_voto.get('signal')}</code> ({float(omega_voto.get('confidence') or 0):.0%})")
        if dual_ask: lines.append(f"\n🔁 <b>Dual-ask</b>: {dual_ask.get('texto','')}")
        lines.append(f"\n<i>{_now_utc_str()}</i>")
        html = "\n".join(lines)
        md = html.replace("<b>","**").replace("</b>","**").replace("<code>","`").replace("</code>","`")
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=sev, alert_type=f"CONSENSUS_{signal_type.upper()}")
    @staticmethod
    def cimatica_consistente(patron_id: int, clave: str, frecuencia: int, event_class=None, ambito: str = "general", id_nodo=None) -> FormattedMessage:
        subj = f"[SENTINEL] CIMATICA CONSISTENTE - patron {patron_id} x{frecuencia}"
        nodo = f" · nodo #{id_nodo}" if id_nodo is not None else ""
        ec = f" asoc. {event_class}" if event_class else " (sin clase aun)"
        desc = (
            "Patrón repetido 3+ veces — deja de ser coincidencia y se vuelve firma. "
            "Revisar entrenamiento del Padre. Como ya hay registro, va al reporte horario; no pagina."
        )
        html = (
            f"<b>CIMATICA CONSISTENTE</b><br>"
            f"<b>Patron:</b> <code>{patron_id}</code>{nodo} ({ambito})<br>"
            f"<b>Frecuencia:</b> <code>{frecuencia} veces</code>{ec}<br>"
            f"<b>Clave:</b> <code>{clave[:64]}</code><br>"
            f"<b>Que significa:</b> {desc}<br>"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**CIMATICA CONSISTENTE** Patron {patron_id}{nodo} x{frecuencia}{ec}"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=Severity.AMARILLO, alert_type="CIMATICA")

    @staticmethod
    def cimatica_nuevo(patron_id: int, clave: str, ambito: str = "general", id_nodo=None, event_class=None) -> FormattedMessage:
        subj = f"[SENTINEL] CIMATICA NUEVO — patron {patron_id}"
        nodo = f" · nodo #{id_nodo}" if id_nodo is not None else ""
        ec = f" asoc. {event_class}" if event_class else ""
        html = (
            f"🆕 <b>CIMATICA SIN PRECEDENTES</b>\n\n"
            f"<b>Patrón:</b> <code>{patron_id}</code>{nodo} ({ambito}){ec}\n"
            f"<b>Clave:</b> <code>{(clave or '')[:64]}</code>\n"
            f"<b>Qué significa:</b> esta combinación de telemetría no estaba en "
            f"<code>tbl_cimatica_patrones</code> (frecuencia=1, NUEVO). "
            f"No es un sismo ni un pronóstico — es un patrón que el sistema no había visto.\n"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**CIMATICA NUEVO** Patron {patron_id}{nodo}"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=Severity.AMARILLO, alert_type="CIMATICA_NUEVO")

    @staticmethod
    def firma_nueva(bot_name: str, event_class: str, firma_id: Optional[int] = None, recurrencia: int = 1) -> FormattedMessage:
        subj = f"[SENTINEL] FIRMA NUEVA — {bot_name} {event_class}"
        fid = f" id={firma_id}" if firma_id else ""
        html = (
            f"🆕 <b>FIRMA SIN PRECEDENTES</b>\n\n"
            f"<b>Bot:</b> <code>{bot_name}</code>  <b>Clase:</b> <code>{event_class}</code>{fid}\n"
            f"<b>Recurrencia:</b> <code>{recurrencia}</code> (estado <code>nueva</code>)\n"
            f"<b>Qué significa:</b> TBL_FIRMAS no tenía este patrón. Las firmas recurrentes "
            f"ya no pagan — van al reporte horario.\n"
            f"<i>{_now_utc_str()}</i>"
        )
        md = f"**FIRMA NUEVA** {bot_name} {event_class}"
        return FormattedMessage(html=html, markdown=md, plain=_strip_tags(html), subject=subj, severity=Severity.AMARILLO, alert_type="FIRMA_NUEVA")

    @staticmethod
    def muro_breach(muro_tipo: str, walls_active: Optional[int] = None, novel: bool = False) -> FormattedMessage:
        subj = f"[SENTINEL] MURO {'NUEVO ' if novel else ''}{muro_tipo}"
        n = f"{walls_active}/5" if walls_active is not None else "n/d"
        kind = "MURO_BREACH_NUEVO" if novel else "MURO_BREACH"
        html = (
            f"🧱 <b>MURO {'SIN PRECEDENTES' if novel else 'BREACH'}</b>\n\n"
            f"<b>Tipo:</b> <code>{muro_tipo}</code>  <b>Activos:</b> <code>{n}</code>\n"
            f"<b>Qué significa:</b> cuántas de las 5 barreras de precursores se encendieron. "
            f"{'Este tipo de rotura no tenía registro previo.' if novel else 'Ya se había visto este tipo; entra al reporte horario.'}\n"
            f"<i>{_now_utc_str()}</i>"
        )
        sev = Severity.ROJO if novel else Severity.AMARILLO
        return FormattedMessage(html=html, markdown=html, plain=_strip_tags(html), subject=subj, severity=sev, alert_type=kind)

    @staticmethod
    def sin_precedente(inner: FormattedMessage) -> str:
        """Wrap an unprecedented event with a clear Spanish header for Telegram."""
        return (
            f"🚨 <b>SIN PRECEDENTES — aviso inmediato</b>\n"
            f"<i>El Padre no tenía registro de esto. Los precursores de siempre van en el reporte horario.</i>\n\n"
            f"{inner.html}"
        )

    @staticmethod
    def reporte_resumen(fantasma: float, muro: str, precursores: list, consenso: str = "") -> FormattedMessage:
        n = len(precursores)
        tabla = ""
        if precursores:
            tabla = "<b>Precursores</b> (qué se vio; no son pings ni tips)<br>"
            for r in precursores[:5]:
                tabla += f"- {r.get('tipo', r.get('display_name', ''))} {r.get('conf', '')} {r.get('zona', '')}<br>"
        html = (
            f"<b>SENTINEL OMEGA - RESUMEN</b><br>"
            f"<b>Fantasma:</b> <code>{fantasma:.1f}</code> — estrés geofísico  "
            f"<b>Muro:</b> <code>{muro}</code> — barreras 1–5  "
            f"<b>Precursores:</b> <code>{n}</code><br>"
            f"{tabla}"
            f"<b>Consenso:</b> {consenso or ''}<br>"
            f"<i>{_now_utc_str()}</i> - ver estado/REPORTE.md"
        )
        return FormattedMessage(html=html, markdown=html, plain=_strip_tags(html), subject=f"[SENTINEL] RESUMEN Fantasma {fantasma:.1f}", severity=Severity.AZUL, alert_type="RESUMEN")

    @staticmethod
    def sistema_online() -> FormattedMessage:
        return FormattedMessage(
            html="🔵 <b>SISTEMA ONLINE</b>\nSentinel Omega vigilando telemetría y precursores. El Padre agrupa avisos en un reporte cada hora.",
            markdown="**SISTEMA ONLINE**",
            plain="SISTEMA ONLINE",
            subject="[SENTINEL] Sistema ONLINE",
            severity=Severity.AZUL,
            alert_type="ONLINE",
        )
    @staticmethod
    def sistema_dead(minutes: float) -> FormattedMessage:
        return FormattedMessage(
            html=(
                f"💀 <b>FALLO DE CICLO PRINCIPAL</b>\n\n"
                f"Sin datos recientes (~{int(minutes)} min). No hay registro de un ciclo sano.\n"
                f"Qué significa: el loop del Padre dejó de escribir. Revisar launcher / orchestrator."
            ),
            markdown=f"**FALLO DE CICLO** — {int(minutes)} min",
            plain=f"FALLO {int(minutes)} min",
            subject="[SENTINEL] FALLO DE CICLO",
            severity=Severity.ROJO,
            alert_type="SYSTEM_DEAD",
        )
    @staticmethod
    def heartbeat(status_line: str) -> FormattedMessage:
        return FormattedMessage(
            html=f"💓 <b>REPORTE DE ESTADO</b>\n{status_line}\n<i>{_now_utc_str()}</i>",
            markdown=f"**REPORTE DE ESTADO**\n{status_line}",
            plain=status_line,
            subject="[SENTINEL] Heartbeat",
            severity=Severity.AZUL,
            alert_type="HEARTBEAT",
        )
class AlertService:
    def __init__(self, dry_run: Optional[bool] = None):
        if dry_run is None: dry_run = os.environ.get("SENTINEL_DRY_RUN","").lower() in ("1","true","yes")
        self.dry_run = dry_run
    def dispatch(self, msg: FormattedMessage, channels: Optional[List[str]]=None, conn=None, cooldown: Optional[int]=None, extra: Optional[Dict]=None) -> Dict[str, bool]:
        if channels is None: channels = ["telegram","correo","log"]
        results: Dict[str,bool] = {}
        if "log" in channels:
            logger.info(f"ALERT [{msg.severity.value}/{msg.alert_type}] {msg.subject}")
            results["log"] = True
        if "telegram" in channels:
            try:
                from sentinel_omega.infrastructure.messaging.consenso_vigilante import get_vigilante
                vig = get_vigilante(dry_run=self.dry_run)
                routed = vig.ingest(msg, extra=extra, conn=conn)
                results["telegram"] = bool(routed.get("sent") or routed.get("action") == "buffered")
                results["telegram_action"] = routed.get("action")  # type: ignore[assignment]
            except Exception as e:
                logger.error(f"Telegram vigilante dispatch failed: {e}")
                results["telegram"] = False
        if "correo" in channels and conn is not None:
            try:
                from sentinel_omega.infrastructure.api.correo import encolar_correo
                encolar_correo(conn, asunto=msg.subject, cuerpo=msg.plain + "\n\n" + msg.html, tipo="ALERTA")
                results["correo"] = True
            except Exception as e:
                logger.error(f"Correo dispatch failed: {e}")
                results["correo"] = False
        return results
    def flush_digest(self, snapshot: Optional[Dict]=None) -> bool:
        """Hourly concentrado. Always attempts to send (dry_run logs only)."""
        from sentinel_omega.infrastructure.messaging.consenso_vigilante import get_vigilante
        rec = get_vigilante(dry_run=self.dry_run).flush_digest(force=True, snapshot=snapshot)
        return bool(rec.sent)
    def centinela_threat(self, risk: float, bz: float, wind: float, schumann: Optional[float]=None) -> Optional[FormattedMessage]:
        th_warn = float(os.environ.get("TG_TH_RISK_WARN","0.60"))
        th_crit = float(os.environ.get("TG_TH_RISK_CRIT","0.75"))
        th_bz = float(os.environ.get("TG_TH_BZ_CRACK","-5.0"))
        th_wind = float(os.environ.get("TG_TH_WIND_STORM","600"))
        r = risk/10.0 if risk>1.5 else risk
        if r >= th_crit: return AlertTemplates.centinela_critico(r, bz, wind, schumann)
        if bz <= th_bz: return AlertTemplates.centinela_grieta(bz)
        if wind >= th_wind: return AlertTemplates.centinela_tormenta(wind)
        if r >= th_warn: return AlertTemplates.centinela_advertencia(r, bz, wind)
        return None
