#!/usr/bin/env python3
"""Telegram Bot — Consensus Expert Agent + Sentinel Omega Bridge

Commands: /task, /concilio, /audit, /status, /reporte, /queue, /blackboard, /cancel
Alert delivery policy (Sentinel Padre / consenso_vigilante):
  - Hourly digest ALWAYS
  - Immediate Telegram ONLY for unprecedented events
This Consensus bot primarily handles interactive /task (+ status reports).
Alerts arrive via alert_queue poller when Sentinel enqueues them.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode as TGParseMode
from telegram.error import InvalidToken
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from alert_queue import alert_queue
from engine.orchestrator import ConsensusOrchestrator
from memory.blackboard import Blackboard
from memory.shared_context import SharedMemory

ParseMode = TGParseMode.HTML

_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)
load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
CONSENSUS_CONFIG = os.environ.get("CONSENSUS_CONFIG", "config.yaml")
SENTINEL_ROOT = os.environ.get(
    "SENTINEL_OMEGA_ROOT", "/home/deamon/workspaces/sentinel_omega"
)
TELEGRAM_WEBAPP_URL = os.environ.get("TELEGRAM_WEBAPP_URL", "").strip()
# El tunel rapido de Cloudflare publica una URL distinta cada vez que arranca y
# la escribe en este log (scripts/run_cloudflared_mini.sh, que lo trunca).
MINI_APP_TUNEL_LOG = Path(__file__).resolve().parent / "logs" / "cloudflared-mini.log"
# Valor VIVO de la URL. Arranca con lo que diga el .env y lo actualiza
# vigilar_url_mini_app() cuando el tunel cambia, sin reiniciar el bot.
_webapp_url_actual: Optional[str] = TELEGRAM_WEBAPP_URL
CONSENSUS_DASHBOARD_URL = os.environ.get(
    "CONSENSUS_DASHBOARD_URL", "http://127.0.0.1:8002"
).strip()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s",
)
# httpx registra la URL completa de cada peticion en INFO. Contra la API de
# Telegram esa URL LLEVA EL TOKEN, y termina en journald en claro y para
# siempre. Callamos a los clientes HTTP; sus errores siguen saliendo.
for _ruidoso in ("httpx", "httpcore", "telegram.ext", "telegram.request"):
    logging.getLogger(_ruidoso).setLevel(logging.WARNING)

# ...pero callar loggers NO BASTA: python-telegram-bot registra el traceback
# de InvalidToken a nivel ERROR, y el token viaja DENTRO del texto de la
# excepcion. Perseguir logger por logger es una carrera que se pierde. En vez
# de eso redactamos en la salida: el formateador ve el mensaje ya renderizado
# y el traceback completo, asi que es el ultimo punto por el que todo pasa.
# Sin \b inicial a proposito: en la URL de la API el token viene pegado al
# prefijo "bot" (…/bot8460857489:AA…), y una frontera de palabra ahi no
# existe, asi que \b haria fallar justo el caso mas comun.
_RE_TOKEN = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")


def _redactar_secretos(texto: str) -> str:
    """Sustituye cualquier token de Telegram por bot_id + marca.

    Conserva el bot_id (publico) para poder diagnosticar de que bot se
    trata, y descarta el secreto.
    """
    return _RE_TOKEN.sub(lambda m: m.group(0).split(":", 1)[0] + ":<REDACTADO>", texto)


class _FormateadorSinSecretos(logging.Formatter):
    """Formateador que redacta tokens en mensaje Y traceback."""

    def format(self, record: logging.LogRecord) -> str:
        return _redactar_secretos(super().format(record))


for _h in logging.getLogger().handlers:
    _h.setFormatter(
        _FormateadorSinSecretos("%(asctime)s | %(levelname)-8s | %(name)s: %(message)s")
    )

logger = logging.getLogger(__name__)


def _bot_id_publico(token: str) -> str:
    """Devuelve solo el bot_id (lo anterior a ':'), que no es secreto.

    Permite identificar en los logs de que bot se habla sin escribir nunca
    la credencial.
    """
    if not token:
        return "<sin token>"
    bot_id = token.split(":", 1)[0]
    return bot_id if bot_id.isdigit() else "<token con formato invalido>"

orchestrator: Optional[ConsensusOrchestrator] = None
shared_memory: Optional[SharedMemory] = None
active_jobs: Dict[int, Dict] = {}
_config_cache: Optional[Dict[str, Any]] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def load_project_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    cfg_path = Path(CONSENSUS_CONFIG)
    if not cfg_path.is_absolute():
        cfg_path = _project_root() / cfg_path
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Could not load config %s: %s", cfg_path, e)
        _config_cache = {}
    return _config_cache


def sessions_dir() -> Path:
    cfg = load_project_config()
    rel = ((cfg.get("concilio") or {}).get("sessions_dir")) or "data/sessions"
    p = Path(rel)
    if not p.is_absolute():
        p = _project_root() / p
    return p


def webapp_url_ok() -> Optional[str]:
    """Telegram Mini Apps require a public HTTPS URL."""
    url = _webapp_url_actual or ""
    if url.lower().startswith("https://"):
        return url
    return None


def url_tunel_en_log(log_path: Optional[Path] = None) -> Optional[str]:
    """Ultima URL que cloudflared publico en su log, con la ruta /mini.

    El script del tunel trunca el log en cada arranque, asi que la ultima que
    aparece es la del tunel que corre ahora.
    """
    ruta = log_path or MINI_APP_TUNEL_LOG
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", texto)
    return f"{urls[-1]}/mini" if urls else None


async def url_responde(url: str, timeout: float = 6.0) -> bool:
    """Que la URL contesta de verdad, ANTES de ponerla en el boton.

    El log puede traer la URL de un tunel que ya murio; registrarla deja el
    boton tan roto como estaba.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            res = await client.get(url)
        return res.status_code == 200
    except Exception:
        return False


def format_blackboard(bb: Blackboard) -> str:
    consensus_score = html.escape(str(bb.consensus_score))
    task_id = html.escape(bb.task_id)
    rounds = html.escape(str(bb.refinement_rounds))
    concilio_rounds = html.escape(str(getattr(bb, "concilio_rounds", 0)))
    synthesis = html.escape(bb.final_synthesis[:3500])
    # El encabezado debe decir lo que paso. Antes rezaba "Consenso Final"
    # tambien cuando no hubo consenso, con la advertencia degradada a una
    # vineta de segunda linea: una respuesta de 73 llegaba bajo un titulo
    # que afirmaba justo lo contrario.
    # La VIA DIRECTA no pasa por el concilio: decir «consenso» o «no aprobada
    # por el Concilio» seria falso. Tiene sus propios dos desenlaces.
    via = (getattr(bb, "shared_notes", None) or {}).get("via", "")
    if via == "directa_verificada":
        cabecera = (f"✅ <b>Verificado por ejecución</b> · vía directa "
                    f"(<code>{consensus_score}</code>% sobre la línea base)")
    elif via == "directa_sin_verificar":
        cabecera = ("⚠️ <b>SIN VERIFICAR</b> · vía directa\n"
                    "<i>El enunciado no permite construir casos fiables: el código "
                    "no se comprobó ejecutándolo. Revísalo antes de usarlo.</i>")
    elif bb.consensus_reached:
        cabecera = f"✅ <b>Consenso alcanzado</b> (Score: <code>{consensus_score}</code>/100)"
    else:
        # Sin default inventado: si la pizarra no trae umbral (snapshot
        # anterior a este campo) se dice que se desconoce, no un numero
        # plausible que podria contradecir a config.yaml.
        _u = getattr(bb, "consensus_threshold", 0)
        if _u:
            _bar = f"por debajo del umbral <code>{html.escape(str(_u))}</code>"
        else:
            _bar = "no alcanzó el umbral <i>(no registrado en este snapshot)</i>"
        cabecera = (
            f"⚠️ <b>SIN CONSENSO</b> — score <code>{consensus_score}</code>/100, "
            f"{_bar}\n"
            f"<i>Síntesis entregada como borrador; no aprobada por el Concilio.</i>"
        )
    if via.startswith("directa"):
        linea_rondas = "⚡ Vía directa: sin concilio"
    else:
        linea_rondas = (f"🔄 Rondas del Concilio: <code>{concilio_rounds}</code>"
                        f" | refinamientos de código: <code>{rounds}</code>")
    lines = [
        cabecera,
        f"🆔 Task: <code>{task_id}</code>",
        linea_rondas,
        "",
        synthesis,
    ]
    text = "\n".join(lines)
    if len(text) > 4000:
        truncated_synthesis = html.escape(bb.final_synthesis[:3000]) + "\n…<i>truncado</i>"
        lines[-1] = truncated_synthesis
        text = "\n".join(lines)
    return text


def format_timeline(bb: Blackboard) -> str:
    if not bb.execution_timeline:
        return "<i>(sin eventos)</i>"
    lines = ["📋 <b>Timeline de ejecución:</b>"]
    for ev in bb.execution_timeline[-8:]:
        icon = {
            "RESEARCH": "🔍",
            "CODING": "💻",
            "REVIEW": "⚖️",
            "REFINING": "🛠️",
            "SYNTHESIS": "✨",
        }.get(ev.get("stage"), "🤖")
        agent = html.escape(ev.get("agent", "?"))
        message = html.escape(ev.get("message", "")[:120])
        lines.append(f"{icon} <b>{agent}</b> — {message}")
    return "\n".join(lines)


def _ts_local(ts: Optional[float]) -> str:
    if not ts:
        return "N/A"
    try:
        from datetime import timedelta

        dt = datetime.fromtimestamp(float(ts), tz=timezone.utc) - timedelta(hours=6)
        return dt.strftime("%d/%m %H:%M") + " CT"
    except Exception:
        return "N/A"


def ollama_running_models() -> List[str]:
    cfg = load_project_config()
    host = ((cfg.get("ollama") or {}).get("host")) or "http://127.0.0.1:11434"
    try:
        import httpx

        with httpx.Client(timeout=3.0) as client:
            res = client.get(f"{host.rstrip('/')}/api/ps")
            if res.status_code != 200:
                return []
            models = res.json().get("models") or []
            names = []
            for m in models:
                name = m.get("name") or m.get("model") or ""
                if name:
                    names.append(name)
            return names
    except Exception:
        return []


def last_concilio_summary() -> str:
    """Safe summary of the newest data/sessions/*.concilio (no secrets)."""
    sdir = sessions_dir()
    if not sdir.is_dir():
        return "📂 Sesiones: <i>directorio ausente</i>"
    files = sorted(sdir.glob("*.concilio"), key=lambda p: p.stat().st_mtime, reverse=True)
    count = len(files)
    if not files:
        return f"📂 Sesiones: <code>0</code> en <code>{html.escape(str(sdir.name))}</code>"
    try:
        doc = json.loads(files[0].read_text(encoding="utf-8"))
    except Exception as e:
        return (
            f"📂 Sesiones: <code>{count}</code>\n"
            f"⚠️ Última ilegible: {html.escape(str(e)[:80])}"
        )
    sid = html.escape(str(doc.get("session_id") or files[0].stem)[:32])
    task = html.escape((doc.get("task") or "")[:100] or "(sin task)")
    rnd = html.escape(str(doc.get("round", "?")))
    scores = doc.get("scores") or []
    if scores:
        last = scores[-1]
        score_txt = (
            f"{html.escape(str(last.get('score')))}/100 "
            f"({'PASS' if last.get('passed') else 'FAIL'})"
        )
    else:
        score_txt = "sin score"
    updated = _ts_local(doc.get("updated_at") or files[0].stat().st_mtime)
    return (
        f"📂 Sesiones: <code>{count}</code>\n"
        f"🧾 Última: <code>{sid}</code> @ {html.escape(updated)}\n"
        f"📝 Task: {task}\n"
        f"🔄 Ronda: <code>{rnd}</code> | Score: {score_txt}"
    )


def concilio_health_block() -> str:
    cfg = load_project_config()
    consensus = cfg.get("consensus") or {}
    concilio = cfg.get("concilio") or {}
    roles = cfg.get("roles") or {}
    threshold = consensus.get("threshold_score", 85)
    sequential = bool(concilio.get("sequential", True))
    worker = concilio.get("worker_model") or (roles.get("researcher") or {}).get("model") or "?"
    arbiter = concilio.get("arbiter_model") or (roles.get("optimizer") or {}).get("model") or "?"
    max_rounds = consensus.get("max_refinement_rounds", 3)
    inject = bool(concilio.get("inject_sentinel_architecture", False))
    seq_txt = "sí" if sequential else "no"
    return (
        f"⚖️ <b>Concilio</b>\n"
        f"Umbral: <code>{html.escape(str(threshold))}</code> | "
        f"Secuencial: <code>{seq_txt}</code> | "
        f"Máx rondas: <code>{html.escape(str(max_rounds))}</code>\n"
        f"Modelos: worker <code>{html.escape(str(worker))}</code> → "
        f"árbitro <code>{html.escape(str(arbiter))}</code>\n"
        f"Inject Sentinel: <code>{'on' if inject else 'off'}</code>"
    )


def alert_queue_block() -> str:
    try:
        stats = alert_queue.get_stats()
    except Exception as e:
        return f"📬 Cola: error — {html.escape(str(e)[:80])}"
    lines = [
        "📬 <b>Cola de alertas</b>",
        f"Pendientes: <code>{stats.get('size', 0)}</code> | "
        f"Encolados: <code>{stats.get('total_enqueued', 0)}</code> | "
        f"Enviados: <code>{stats.get('total_sent', 0)}</code> | "
        f"Fallidos: <code>{stats.get('total_failed', 0)}</code>",
    ]
    # Un aviso descartado o colgado en vuelo no debe quedarse callado: es lo
    # unico que dice que algo no llego.
    en_vuelo = stats.get("en_vuelo", 0)
    descartados = stats.get("descartados", 0)
    if en_vuelo or descartados:
        lines.append(
            f"⚠️ En vuelo: <code>{en_vuelo}</code> | "
            f"Descartados: <code>{descartados}</code> "
            f"(<code>data/alert_queue_dead.json</code>)"
        )
    la = stats.get("last_alert")
    if la:
        lines.append(
            f"Última: <code>{html.escape(str(la.get('priority', '?')))}</code> "
            f"{html.escape(str(la.get('title', ''))[:60])} "
            f"@ {_ts_local(la.get('timestamp'))}"
        )
    return "\n".join(lines)


def ollama_unload_note() -> str:
    running = ollama_running_models()
    if not running:
        return (
            "🧊 <b>Ollama</b>: idle (sin modelo en VRAM) — normal entre tareas; /task carga el ligero — "
            "listo para pipeline secuencial."
        )
    names = ", ".join(html.escape(n) for n in running[:6])
    extra = f" (+{len(running) - 6})" if len(running) > 6 else ""
    return (
        f"🔥 <b>Ollama cargados</b>: {names}{extra}\n"
        f"<i>Concilio descarga entre etapas (un modelo a la vez).</i>"
    )


def sentinel_health() -> str:
    root = Path(SENTINEL_ROOT)
    db = root / "data" / "SENTINEL_OMEGA_PRO.db"
    if not db.exists():
        return "🔴 <b>Sentinel Omega</b>: DB no encontrada (solo lectura)"
    import sqlite3

    try:
        conn = sqlite3.connect(str(db))
        cur = conn.execute("SELECT MAX(timestamp), COUNT(*) FROM TBL_CICLOS")
        last_ciclo, total = cur.fetchone()
        cur = conn.execute(
            "SELECT MAX(timestamp), COUNT(*) FROM TBL_PRECURSORES_COSMICOS"
        )
        _last_prec, prec_total = cur.fetchone()
        cur = conn.execute(
            "SELECT MAX(timestamp), COUNT(*) FROM TBL_JUEZ_AUDITORIA"
        )
        _last_juez, juez_total = cur.fetchone()
        conn.close()
        last_str = _ts_local(last_ciclo) if last_ciclo else "N/A"
        return (
            f"🟢 <b>Sentinel Omega</b> — Online (read-only)\n"
            f"📊 Ciclos: <code>{total}</code> (último: {html.escape(last_str)})\n"
            f"🛰️ Precursores: <code>{prec_total}</code>\n"
            f"⚖️ Auditorías Juez: <code>{juez_total}</code>\n"
            f"💾 DB: <code>{html.escape(db.name)}</code>"
        )
    except Exception as e:
        return f"🟡 <b>Sentinel Omega</b>: Error leyendo BD — {html.escape(str(e))}"


def _is_sentinel_status_query(prompt: str) -> bool:
    p = (prompt or "").lower()
    keys = (
        "evento", "eventos", "precursor", "precursores", "alerta", "alertas",
        "muro", "fantasma", "ciclo", "riesgo", "sismo", "schumann", "sentinel",
        "próximo", "proximo", "próximos", "proximos", "qué hay", "que hay",
        "estado del sistema", "status sentinel",
    )
    return any(k in p for k in keys)


def sentinel_proximos_eventos() -> str:
    """Read-only live snapshot from Sentinel prod DB — never invent events."""
    root = Path(SENTINEL_ROOT)
    db = root / "data" / "SENTINEL_OMEGA_PRO.db"
    if not db.exists():
        return "🔴 Sentinel DB no encontrada — no puedo listar eventos reales."
    import sqlite3
    import json as _json
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        ciclo = conn.execute(
            "SELECT id, nivel_riesgo, fantasma, precursors_count, precursor_types, "
            "muro_walls_active, muro_breach, created_at, timestamp "
            "FROM TBL_CICLOS ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not ciclo:
            conn.close()
            return "🟡 Sin ciclos en DB."
        muro = conn.execute(
            "SELECT walls_active, total_walls, muro_breach, risk_label, "
            "wall_geofisico, wall_atmosferico, wall_oceanico, wall_solar, wall_financiero, "
            "active_types_json, created_at "
            "FROM TBL_MURO_EVENTOS ORDER BY id DESC LIMIT 1"
        ).fetchone()
        tele = conn.execute(
            "SELECT schumann_hz, schumann_activity, bz_nT, viento_km_s, kp, fantasma, nivel_riesgo "
            "FROM TBL_PRECURSORES_COSMICOS ORDER BY id DESC LIMIT 1"
        ).fetchone()
        try:  # muro de lags: ventana temporal con countdown (tabla puede no existir aún)
            ml = conn.execute(
                "SELECT clases, fecha_inicio, fecha_fin, detectado_en "
                "FROM tbl_muro_lags_estado WHERE id=1 AND activo=1"
            ).fetchone()
        except Exception:
            ml = None
        conn.close()
        tipos = ciclo["precursor_types"]
        try:
            if isinstance(tipos, str) and tipos.strip().startswith("["):
                tipos_list = _json.loads(tipos)
            elif isinstance(tipos, str) and tipos.strip():
                tipos_list = [x.strip() for x in tipos.replace(";", ",").split(",") if x.strip()]
            else:
                tipos_list = []
        except Exception:
            tipos_list = [str(tipos)] if tipos else []
        muro_types = []
        if muro and muro["active_types_json"]:
            try:
                raw = muro["active_types_json"]
                muro_types = _json.loads(raw) if isinstance(raw, str) else list(raw or [])
            except Exception:
                muro_types = []
        walls = []
        if muro:
            for name, flag in (
                ("geofísico", muro["wall_geofisico"]),
                ("atmosférico", muro["wall_atmosferico"]),
                ("oceánico", muro["wall_oceanico"]),
                ("solar", muro["wall_solar"]),
                ("financiero", muro["wall_financiero"]),
            ):
                if flag:
                    walls.append(name)
        when = html.escape(str(ciclo["created_at"] or "N/A"))
        lines = [
            "📡 <b>Próximos / eventos activos (Sentinel Omega)</b>",
            f"<i>Ciclo #{ciclo['id']} · {when} UTC · datos reales DB</i>",
            "",
            f"🎚 Riesgo: <b>{html.escape(str(ciclo['nivel_riesgo']))}</b>",
            f"👻 Fantasma: <code>{float(ciclo['fantasma'] or 0):.2f}</code>",
            f"🧱 Muro: <code>{int(ciclo['muro_walls_active'] or 0)}/5</code> "
            f"breach=<code>{int(ciclo['muro_breach'] or 0)}</code>",
        ]
        if walls:
            lines.append("   activos: " + ", ".join(walls))
        if muro_types:
            lines.append("   tipos muro: " + html.escape(", ".join(map(str, muro_types))))
        if ml:
            try:
                from datetime import datetime as _dt
                dini = _dt.strptime(ml["fecha_inicio"], "%Y-%m-%d").date()
                dfin = _dt.strptime(ml["fecha_fin"], "%Y-%m-%d").date()
                hoy = _dt.utcnow().date()
                rini = max(0, (dini - hoy).days)
                rfin = max(0, (dfin - hoy).days)
                clases_ml = ", ".join(_json.loads(ml["clases"] or "[]"))
                lines.append("")
                lines.append(
                    f"⏳ <b>Ventana temporal (muro de lags)</b>: faltan ~{rini}-{rfin} días "
                    f"(hasta {html.escape(str(ml['fecha_fin']))})"
                )
                if clases_ml:
                    lines.append(f"   convergen: {html.escape(clases_ml)}")
            except Exception:
                pass
        lines.append("")
        lines.append(f"🛰️ Precursores en ciclo: <code>{int(ciclo['precursors_count'] or 0)}</code>")
        if tipos_list:
            for t in tipos_list[:12]:
                lines.append(f"  · {html.escape(str(t))}")
        else:
            lines.append("  · (sin detalle de tipos en este ciclo)")
        if tele:
            lines.append("")
            lines.append(
                f"📻 Schumann <code>{float(tele['schumann_hz'] or 0):.2f}</code> Hz · "
                f"act <code>{float(tele['schumann_activity'] or 0):.2f}</code> · "
                f"Bz <code>{float(tele['bz_nT'] or 0):.2f}</code> · "
                f"Kp <code>{float(tele['kp'] or 0):.2f}</code>"
            )
        lines.append("")
        lines.append("<i>Esto no es un pronóstico de epicentro. Solo lecturas Sentinel.</i>")
        return "\n".join(lines)
    except Exception as e:
        return f"🟡 Error leyendo eventos Sentinel: {html.escape(str(e))}"



def build_status_report(full: bool = True) -> str:
    """Enriched status /reporte — no secrets."""
    parts = [
        "📊 <b>Reporte Consenso + Sentinel</b>",
        "",
        concilio_health_block(),
        "",
        last_concilio_summary(),
        "",
        ollama_unload_note(),
        "",
        alert_queue_block(),
        "",
        sentinel_health(),
    ]
    if full:
        parts.extend(
            [
                "",
                "📜 <b>Política alertas (Padre)</b>",
                "• Digest horario: <b>siempre</b>",
                "• Inmediato: solo eventos <b>sin precedentes</b>",
                "• Este bot: /task ligero · /concilio heavy · reportes; cola vía <code>alert_queue</code>",
            ]
        )
        dash = html.escape(CONSENSUS_DASHBOARD_URL or "(no set)")
        parts.append(f"🖥 Dashboard: <code>{dash}</code>")
        wurl = webapp_url_ok()
        if wurl:
            parts.append(f"📱 Mini App: <code>{html.escape(wurl)}</code>")
        elif TELEGRAM_WEBAPP_URL:
            parts.append(
                "📱 Mini App: URL no HTTPS — botón omitido "
                "(Telegram exige HTTPS público)"
            )
        else:
            parts.append(
                "📱 Mini App: configura <code>TELEGRAM_WEBAPP_URL</code> (HTTPS)"
            )
    text = "\n".join(parts)
    if len(text) > 3900:
        text = text[:3850] + "\n…<i>truncado</i>"
    return text


def status_payload_json() -> Dict[str, Any]:
    """JSON for miniapp /api/mini/status — no secrets."""
    cfg = load_project_config()
    consensus = cfg.get("consensus") or {}
    concilio = cfg.get("concilio") or {}
    roles = cfg.get("roles") or {}
    sdir = sessions_dir()
    files = (
        sorted(sdir.glob("*.concilio"), key=lambda p: p.stat().st_mtime, reverse=True)
        if sdir.is_dir()
        else []
    )
    last = None
    if files:
        try:
            doc = json.loads(files[0].read_text(encoding="utf-8"))
            scores = doc.get("scores") or []
            last = {
                "session_id": str(doc.get("session_id") or files[0].stem)[:32],
                "task": (doc.get("task") or "")[:120],
                "round": doc.get("round"),
                "score": scores[-1].get("score") if scores else None,
                "passed": scores[-1].get("passed") if scores else None,
                "updated_at": doc.get("updated_at"),
            }
        except Exception:
            last = {"error": "unreadable"}
    try:
        qstats = alert_queue.get_stats()
        qstats = dict(qstats)
        qstats["file_path"] = Path(str(qstats.get("file_path", ""))).name
    except Exception as e:
        qstats = {"error": str(e)[:80]}
    running = ollama_running_models()
    return {
        "ok": True,
        "concilio": {
            "threshold": consensus.get("threshold_score", 85),
            "sequential": bool(concilio.get("sequential", True)),
            "max_rounds": consensus.get("max_refinement_rounds", 3),
            "worker_model": concilio.get("worker_model")
            or (roles.get("researcher") or {}).get("model"),
            "arbiter_model": concilio.get("arbiter_model")
            or (roles.get("optimizer") or {}).get("model"),
            "inject_sentinel": bool(
                concilio.get("inject_sentinel_architecture", False)
            ),
            "sessions_count": len(files),
            "last_session": last,
        },
        "ollama": {
            "loaded": running,
            "unloaded_note": "idle — no models loaded"
            if not running
            else "models loaded; Concilio unloads between stages",
        },
        "alert_queue": qstats,
        "dashboard_url": CONSENSUS_DASHBOARD_URL,
        "webapp_url": webapp_url_ok() or "",
        "alert_policy": {
            "hourly_digest": "always",
            "immediate": "unprecedented_only",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
def main_keyboard() -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("🧠 Nueva tarea al Concilio", callback_data="new_task")],
        [InlineKeyboardButton("🔍 Auditoría Sentinel Omega", callback_data="audit_sentinel")],
        [
            InlineKeyboardButton("📊 Estado / Reporte", callback_data="show_report"),
            InlineKeyboardButton("📬 Cola", callback_data="show_queue"),
        ],
        [InlineKeyboardButton("📜 Ver Blackboard activo", callback_data="show_blackboard")],
    ]
    wurl = webapp_url_ok()
    if wurl:
        rows.append(
            [InlineKeyboardButton("📱 Mini App", web_app=WebAppInfo(url=wurl))]
        )
    rows.append([InlineKeyboardButton("❓ Ayuda", callback_data="help")])
    return InlineKeyboardMarkup(rows)


def audit_focus_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔬 Completa", callback_data="audit_full")],
            [InlineKeyboardButton("🧪 Tests", callback_data="audit_tests")],
            [InlineKeyboardButton("🔐 Secretos/Seguridad", callback_data="audit_secrets")],
            [InlineKeyboardButton("📦 Migraciones/DB", callback_data="audit_migrations")],
            [InlineKeyboardButton("⚙️ Automatización/CI", callback_data="audit_automation")],
            [InlineKeyboardButton("🔙 Volver", callback_data="back_main")],
        ]
    )


def is_authorized(update: Update) -> bool:
    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set — allowing all (dev mode)")
        return True
    chat_id = str(update.effective_chat.id)
    allowed = {c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()}
    authorized = chat_id in allowed
    if not authorized:
        logger.warning("Unauthorized access attempt: %s", chat_id)
        if update.message:
            asyncio.create_task(update.message.reply_text("🚫 No autorizado"))
        elif update.callback_query:
            asyncio.create_task(
                update.callback_query.answer("🚫 No autorizado", show_alert=True)
            )
    return authorized


def _chat_id_from(target: Any) -> Optional[int]:
    if isinstance(target, Update):
        if target.effective_chat:
            return target.effective_chat.id
        if target.callback_query and target.callback_query.message:
            return target.callback_query.message.chat_id
        if target.message:
            return target.message.chat_id
    msg = getattr(target, "message", None)
    if msg is not None:
        return msg.chat_id
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🧠 <b>Consenso de Expertos + Sentinel Omega</b>\n\n"
        "Telegram: /task = ligero (fast_ask); /concilio = Concilio completo (heavy).\n"
        "Alertas: digest horario siempre; inmediato solo sin precedentes.\n\n"
        "¿Qué deseas hacer?",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "<b>Comandos disponibles:</b>\n"
        "/start — Menú principal\n"
        "/task &lt;prompt&gt; — Respuesta rápida (modelo ligero)\n        /concilio &lt;prompt&gt; — Concilio completo (heavy / umbral 85)\n"
        "/audit [foco] — Auditar Sentinel\n"
        "/status — Estado enriquecido (Concilio + cola + sesión)\n"
        "/reporte — Reporte completo + política de alertas\n"
        "/queue — Cola de alertas\n"
        "/blackboard — Pizarra activa\n"
        "/cancel — Cancelar tarea en curso\n\n"
        "<b>Política:</b> digest horario siempre; "
        "Telegram inmediato solo eventos sin precedentes.\n"
        "Este bot: /task ligero · /concilio heavy · Sentinel Padre encola alertas.",
        parse_mode=ParseMode,
    )


async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text(
            "Uso: <code>/task &lt;tu prompt&gt;</code>", parse_mode=ParseMode
        )
        return
    await run_consensus_task(update, prompt)



async def concilio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full Concilio (heavy). Default /task is fast/light."""
    if not is_authorized(update):
        return
    prompt = " ".join(context.args).strip() if context.args else ""
    if not prompt:
        await update.message.reply_text(
            "Uso: <code>/concilio &lt;tu prompt&gt;</code>\n"
            "<i>/task = rápido (ligero). /concilio = pipeline completo.</i>",
            parse_mode=ParseMode,
        )
        return
    await run_full_concilio_task(update, prompt)

async def audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    focus = " ".join(context.args).strip() or ""
    await run_audit(update, focus)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        build_status_report(full=False),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode,
    )


async def reporte_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        build_status_report(full=True),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode,
    )


async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        alert_queue_block(), reply_markup=main_keyboard(), parse_mode=ParseMode
    )


async def blackboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if shared_memory and shared_memory.active_blackboard:
        bb = shared_memory.active_blackboard
        await update.message.reply_text(
            format_blackboard(bb) + "\n\n" + format_timeline(bb),
            parse_mode=ParseMode,
        )
    else:
        await update.message.reply_text("No hay blackboard activa.")


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    chat_id = update.effective_chat.id
    if chat_id in active_jobs:
        del active_jobs[chat_id]
        await update.message.reply_text("✅ Tarea cancelada.")
    else:
        await update.message.reply_text("No hay tarea activa.")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_authorized(update):
        await query.answer("No autorizado", show_alert=True)
        return
    await query.answer()
    data = query.data or ""

    if data == "new_task":
        await query.edit_message_text(
            "📝 Envía tu prompt como mensaje de texto.\n"
            "Ejemplo: <code>Crea una API REST con FastAPI y autenticación JWT</code>",
            parse_mode=ParseMode,
        )
        context.user_data["awaiting_task"] = True

    elif data == "audit_sentinel":
        await query.edit_message_text(
            "🔍 <b>Auditoría Sentinel Omega</b>\nSelecciona foco:",
            reply_markup=audit_focus_keyboard(),
            parse_mode=ParseMode,
        )

    elif data.startswith("audit_"):
        focus_map = {
            "audit_full": "",
            "audit_tests": "tests",
            "audit_secrets": "secretos seguridad",
            "audit_migrations": "migraciones base de datos",
            "audit_automation": "automatización CI/CD",
        }
        focus = focus_map.get(data, "")
        await run_audit(update, focus, edit=True)

    elif data in ("sentinel_status", "show_report", "show_status"):
        await query.edit_message_text(
            build_status_report(full=True),
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )

    elif data == "show_queue":
        await query.edit_message_text(
            alert_queue_block(),
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )

    elif data == "show_blackboard":
        if shared_memory and shared_memory.active_blackboard:
            bb = shared_memory.active_blackboard
            await query.edit_message_text(
                format_blackboard(bb) + "\n\n" + format_timeline(bb),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode,
            )
        else:
            await query.edit_message_text(
                "No hay blackboard activa.", reply_markup=main_keyboard()
            )

    elif data == "help":
        await query.edit_message_text(
            "<b>Comandos:</b>\n"
            "/task &lt;prompt&gt; — Respuesta rápida (ligero)\n            /concilio &lt;prompt&gt; — Concilio completo (heavy)\n"
            "/audit [foco] — Auditoría\n"
            "/status — Estado enriquecido\n"
            "/reporte — Reporte + política\n"
            "/queue — Cola alertas\n"
            "/blackboard — Ver pizarra\n"
            "/cancel — Cancelar\n\n"
            "Digest horario siempre; inmediato solo sin precedentes.",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )

    elif data == "back_main":
        await query.edit_message_text(
            "🧠 <b>Menú principal</b>",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    logger.info(
        "Received message from %s: %s",
        update.effective_chat.id,
        (update.message.text[:50] if update.message and update.message.text else "no text"),
    )
    if context.user_data.get("awaiting_task"):
        context.user_data["awaiting_task"] = False
        prompt = (update.message.text or "").strip()
        if prompt:
            await run_consensus_task(update, prompt)
    else:
        await update.message.reply_text(
            "Usa /task &lt;prompt&gt;, /reporte o el menú /start",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )


async def run_consensus_task(update: Update, prompt: str, edit: bool = False):
    """Telegram default: FAST light path. Full Concilio = /concilio."""
    chat_id = _chat_id_from(update)
    if chat_id is None:
        logger.error("Cannot determine chat_id from update")
        return

    if chat_id in active_jobs:
        msg = "⚠️ Ya hay una tarea en curso. Usa /cancel para cancelarla."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
        return

    boot = (
        "⚡ <b>Respuesta rápida</b> (modelo ligero)...\n"
        "<i>Concilio completo (heavy): /concilio &lt;prompt&gt;</i>"
    )
    if update.callback_query:
        status_msg = await update.callback_query.bot.send_message(
            chat_id=chat_id, text=boot, parse_mode=ParseMode
        )
    else:
        status_msg = await update.message.reply_text(boot, parse_mode=ParseMode)

    active_jobs[chat_id] = {"started": datetime.now(timezone.utc), "prompt": prompt}

    try:
        loop = asyncio.get_event_loop()
        if _is_sentinel_status_query(prompt):
            answer = await loop.run_in_executor(None, sentinel_proximos_eventos)
            body = (
                "⚡ <b>Respuesta rápida · datos Sentinel</b>\n\n"
                + (answer or "(sin datos)")
                + "\n\n<i>Heavy: /concilio · Dashboard web sigue en Concilio completo.</i>"
            )
        else:
            answer = await loop.run_in_executor(None, lambda: orchestrator.fast_ask(prompt, preload_sentinel=True))
            body = (
                "⚡ <b>Respuesta rápida</b>\n\n"
                + html.escape(answer or "(sin texto)")
                + "\n\n<i>Heavy: /concilio · Dashboard web sigue en Concilio completo.</i>"
            )
        active_jobs.pop(chat_id, None)

        if len(body) > 4000:
            body = body[:3990] + "…"
        await status_msg.edit_text(body, reply_markup=main_keyboard(), parse_mode=ParseMode)
    except Exception as e:
        active_jobs.pop(chat_id, None)
        logger.exception("Fast telegram task failed")
        await status_msg.edit_text(
            f"❌ Error: {html.escape(str(e))}",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )


async def run_full_concilio_task(update: Update, prompt: str, edit: bool = False):
    chat_id = _chat_id_from(update)
    if chat_id is None:
        logger.error("Cannot determine chat_id from update")
        return

    if chat_id in active_jobs:
        msg = "⚠️ Ya hay una tarea en curso. Usa /cancel para cancelarla."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
        return

    boot = (
        "🔄 <b>Iniciando Concilio secuencial...</b>\n"
        "🔍 Worker-Research...\n"
        "💻 Worker-Coder...\n"
        "⚖️ Árbitro (umbral 85)..."
    )
    if update.callback_query:
        status_msg = await update.callback_query.bot.send_message(
            chat_id=chat_id, text=boot, parse_mode=ParseMode
        )
    else:
        status_msg = await update.message.reply_text(boot, parse_mode=ParseMode)

    active_jobs[chat_id] = {"started": datetime.now(timezone.utc), "prompt": prompt}

    try:
        loop = asyncio.get_event_loop()
        bb = await loop.run_in_executor(
            None,
            lambda: orchestrator.run_consensus(
                user_prompt=prompt, shared_memory=shared_memory
            ),
        )
        active_jobs.pop(chat_id, None)
        text = format_blackboard(bb) + "\n\n" + format_timeline(bb)
        await status_msg.edit_text(
            text, reply_markup=main_keyboard(), parse_mode=ParseMode
        )
    except Exception as e:
        active_jobs.pop(chat_id, None)
        logger.exception("Consensus task failed")
        await status_msg.edit_text(
            f"❌ Error: {html.escape(str(e))}",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )


async def run_audit(update: Update, focus: str, edit: bool = False):
    chat_id = _chat_id_from(update)
    if chat_id is None:
        logger.error("Cannot determine chat_id from update")
        return

    if chat_id in active_jobs:
        msg = "⚠️ Ya hay una tarea en curso."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        elif update.message:
            await update.message.reply_text(msg)
        return

    label = f"({html.escape(focus)})" if focus else "(completa)"
    boot = (
        f"🔍 <b>Auditoría Sentinel Omega</b> {label}\n"
        "🔍 Worker analizando...\n"
        "💻 Coder revisando...\n"
        "⚖️ Árbitro evaluando...\n"
    )
    if update.callback_query:
        status_msg = await update.callback_query.bot.send_message(
            chat_id=chat_id, text=boot, parse_mode=ParseMode
        )
    else:
        status_msg = await update.message.reply_text(boot, parse_mode=ParseMode)

    active_jobs[chat_id] = {"started": datetime.now(timezone.utc), "audit": focus}

    try:
        loop = asyncio.get_event_loop()
        bb = await loop.run_in_executor(
            None, lambda: orchestrator.audit_project(focus=focus)
        )
        active_jobs.pop(chat_id, None)
        text = format_blackboard(bb) + "\n\n" + format_timeline(bb)
        await status_msg.edit_text(
            text, reply_markup=main_keyboard(), parse_mode=ParseMode
        )
    except Exception as e:
        active_jobs.pop(chat_id, None)
        logger.exception("Audit failed")
        await status_msg.edit_text(
            f"❌ Error en auditoría: {html.escape(str(e))}",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode,
        )


def _texto_interrumpidas(pendientes: List[Dict[str, Any]]) -> str:
    """El aviso, en texto plano a proposito: el enunciado lo escribio el
    operador y puede traer *, _ o backticks que romperian el formateo."""
    n = len(pendientes)
    cabeza = ("⚠️ Se interrumpio una tarea y no llegue a responderte."
              if n == 1 else
              f"⚠️ Se interrumpieron {n} tareas y no llegue a responderte.")
    lineas = [cabeza, ""]
    for s in pendientes[:5]:
        cuando = datetime.fromtimestamp(s["updated_at"]).strftime("%d/%m %H:%M") if s["updated_at"] else "?"
        ronda = s.get("round")
        donde = f"ronda {ronda} del concilio" if ronda else "antes de la primera ronda"
        lineas.append(f"• {cuando} — se corto en la {donde}.")
        tarea = (s["task"] or "").strip().replace("\n", " ")
        if tarea:
            lineas.append(f"  {tarea[:300]}")
    if n > 5:
        lineas.append(f"… y {n - 5} mas.")
    lineas += ["", "No se entrego nada: si la quieres, vuelve a mandarla."]
    return "\n".join(lineas)


async def avisar_sesiones_interrumpidas(application: Application):
    """Al arrancar, avisa de las tareas que murieron a medias.

    Pasa de verdad: el 2026-09-25 un reinicio de Windows corto una tarea del
    concilio a los 10 minutos, con el codigo ya correcto en la pizarra, y el
    operador se quedo esperando una respuesta que nunca iba a llegar.

    Las sesiones solo se marcan cerradas si el aviso SALIO. Si no hay a quien
    avisar, se quedan para el proximo arranque.
    """
    try:
        store = orchestrator.concilio_store
        pendientes = store.sesiones_interrumpidas()
    except Exception as e:  # noqa: BLE001
        logger.error("no se pudieron revisar las sesiones: %s: %s", type(e).__name__, e)
        return
    if not pendientes:
        logger.info("sin tareas interrumpidas")
        return

    chat_ids = [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()] if TELEGRAM_CHAT_ID else []
    if not chat_ids:
        logger.warning("%d tareas interrumpidas pero TELEGRAM_CHAT_ID esta vacio: "
                       "quedan para el proximo arranque", len(pendientes))
        return

    texto = _texto_interrumpidas(pendientes)
    entregado = False
    for chat_id in chat_ids:
        try:
            await application.bot.send_message(chat_id=int(chat_id), text=texto)
            entregado = True
        except Exception as e:  # noqa: BLE001
            logger.error("no se pudo avisar a %s: %s", chat_id, e)
    if not entregado:
        return
    for s in pendientes:
        try:
            doc = store.load(s["session_id"])
            store.cerrar(doc, motivo="interrumpida; avisado al operador al arrancar")
        except Exception as e:  # noqa: BLE001
            logger.error("no se pudo cerrar %s: %s: %s", s["session_id"], type(e).__name__, e)
    logger.info("avisadas %d tareas interrumpidas", len(pendientes))


async def poll_alert_queue(application: Application):
    # Lo que el proceso anterior saco de la cola y no llego a confirmar vuelve
    # a la cabeza. Es el mismo hueco que el de las sesiones cortadas: si el
    # proceso muere entre sacar y enviar, el aviso no esta en ningun archivo.
    recuperados = alert_queue.recover_inflight()
    if recuperados:
        logger.warning(
            "Cola: %d aviso(s) quedaron en vuelo en el arranque anterior, "
            "devueltos a la cola",
            len(recuperados),
        )
    logger.info("🔄 Alert queue poller started")
    while True:
        try:
            alerts = alert_queue.pop_batch(max_count=5)
            for alert in alerts:
                chat_ids = (
                    [c.strip() for c in TELEGRAM_CHAT_ID.split(",") if c.strip()]
                    if TELEGRAM_CHAT_ID
                    else []
                )
                # Un reintento solo va a los chats que faltan: repetirselo a
                # quien ya lo recibio seria duplicarle el aviso.
                destinos = alert.pending_chats or chat_ids
                if not destinos:
                    logger.warning("TELEGRAM_CHAT_ID vacío — el aviso vuelve a la cola")
                    # Sin chats configurados el fallo no es del aviso: no
                    # gasta intentos (si no, la cola entera se descartaria).
                    alert_queue.requeue(alert, contar_intento=False)
                    alert_queue.mark_failed(alert)
                    await asyncio.sleep(5)
                    continue

                fallidos = []
                for chat_id in destinos:
                    try:
                        await application.bot.send_message(
                            chat_id=int(chat_id),
                            text=alert.message,
                            parse_mode=alert.parse_mode,
                        )
                        logger.info(
                            "Alert sent: %s (%s)", alert.title, alert.priority
                        )
                    except Exception as e:
                        fallidos.append(chat_id)
                        logger.error("Failed to send alert to %s: %s", chat_id, e)

                if not fallidos:
                    alert_queue.mark_sent(alert)
                    continue

                # Antes bastaba un chat para darlo por entregado y destruirlo:
                # los demas se quedaban sin el aviso y nadie lo sabia.
                alert.pending_chats = fallidos
                alert_queue.mark_failed(alert)
                if alert_queue.requeue(alert):
                    await asyncio.sleep(5)
                else:
                    logger.error(
                        "Cola: aviso «%s» descartado tras %d intentos, queda en "
                        "data/alert_queue_dead.json",
                        alert.title,
                        alert.attempts,
                    )
        except Exception as e:
            logger.error("Alert queue poller error: %s", e)

        await asyncio.sleep(2)




async def registrar_boton_mini_app(application: Application) -> None:
    """Pone el botón de menú Mini App en cada chat de TELEGRAM_CHAT_ID al arrancar.

    El túnel rápido de Cloudflare cambia de URL al reiniciarse; re-registrar
    en cada arranque evita que el botón quede apuntando a una URL muerta.
    Sin URL HTTPS, regresa el botón al predeterminado para no dejar uno roto.
    Se pone por chat porque el botón por defecto no se estaba quedando.
    Un fallo solo deja un aviso en el log: el bot sigue funcionando.
    """
    from urllib.parse import urlparse
    from telegram import MenuButtonDefault, MenuButtonWebApp

    url = webapp_url_ok()
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
    if not chats:
        logger.info("Mini App: sin TELEGRAM_CHAT_ID, botón no registrado")
        return
    host = urlparse(url).netloc if url else "-"
    boton = (MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=url))
             if url else MenuButtonDefault())
    for chat in chats:
        try:
            await application.bot.set_chat_menu_button(chat_id=int(chat), menu_button=boton)
            logger.info("Mini App: botón %s en un chat (host %s)",
                        "registrado" if url else "regresado al predeterminado", host)
        except Exception as exc:
            logger.warning("Mini App: no se pudo registrar el botón (%s)", type(exc).__name__)


async def vigilar_url_mini_app(application: Application, intervalo: float = 120.0) -> None:
    """Sigue la URL del túnel y re-registra el botón cuando cambia.

    El tunel rapido estrena URL en cada arranque. Hasta ahora el ajuste lo hacia
    `scripts/run_cloudflared_mini.sh`: reescribia TELEGRAM_WEBAPP_URL en el .env
    y MATABA al bot (`pkill -TERM -f /telegram_bot.py`) para que systemd lo
    levantara con el valor nuevo. Eso se llevaba por delante cualquier tarea del
    concilio en curso --- la tarea real del 25-sep duro 9 minutos --- igual que
    el reinicio de Windows del 25-sep 13:16, y por la misma razon: nadie avisaba.
    Ahora el bot se entera solo y no hace falta reiniciarlo.
    """
    global _webapp_url_actual
    from urllib.parse import urlparse

    while True:
        try:
            nueva = url_tunel_en_log()
            if nueva and nueva != _webapp_url_actual:
                if await url_responde(nueva):
                    anterior = urlparse(_webapp_url_actual or "").netloc or "-"
                    _webapp_url_actual = nueva
                    logger.info(
                        "Mini App: el túnel cambió de URL (%s → %s), re-registrando",
                        anterior,
                        urlparse(nueva).netloc,
                    )
                    await registrar_boton_mini_app(application)
                else:
                    logger.warning(
                        "Mini App: el log anuncia %s pero no responde; se queda la anterior",
                        urlparse(nueva).netloc,
                    )
        except Exception as exc:
            logger.warning(
                "Mini App: la vigilancia de la URL falló (%s)", type(exc).__name__
            )
        await asyncio.sleep(intervalo)


def main():
    global orchestrator, shared_memory

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado en entorno")

    logger.info("Inicializando Consensus Orchestrator...")
    orchestrator = ConsensusOrchestrator(config_path=CONSENSUS_CONFIG)
    shared_memory = SharedMemory(db_path=orchestrator.db_path)
    logger.info("✅ Orchestrator listo")
    if TELEGRAM_WEBAPP_URL and not webapp_url_ok():
        logger.warning(
            "TELEGRAM_WEBAPP_URL is set but not HTTPS (%s) — Mini App button omitted",
            TELEGRAM_WEBAPP_URL[:60],
        )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("concilio", concilio_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("reporte", reporte_cmd))
    app.add_handler(CommandHandler("report", reporte_cmd))
    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("blackboard", blackboard_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    async def post_init(application: Application):
        application.create_task(poll_alert_queue(application))
        application.create_task(registrar_boton_mini_app(application))
        application.create_task(vigilar_url_mini_app(application))
        logger.info("🔄 Alert queue poller scheduled")
        await avisar_sesiones_interrumpidas(application)

    app.post_init = post_init

    logger.info("🤖 Bot iniciado — polling...")
    try:
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except InvalidToken:
        # python-telegram-bot incrusta el token EN el mensaje de la excepcion
        # (telegram/_bot.py: "The token `{self._token}` was rejected"). Si la
        # dejamos propagar, el traceback lo escribe en claro en journald, y
        # con Restart= lo reimprime en cada reintento. La tragamos aqui y
        # reportamos solo el bot_id.
        logger.error(
            "Telegram rechazo el token del bot %s. Actualiza "
            "TELEGRAM_BOT_TOKEN en .env y reinicia el servicio.",
            _bot_id_publico(TELEGRAM_BOT_TOKEN),
        )
        raise SystemExit(78)  # EX_CONFIG


if __name__ == "__main__":
    main()