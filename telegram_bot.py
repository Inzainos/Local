#!/usr/bin/env python3
"""
Telegram Bot — Consensus Expert Agent + Sentinel Omega Bridge
Permite consultar al Concilio de Expertos (Nemotron/DeepSeek/Gemma) y ver estado de Sentinel Omega desde Telegram.
"""

import os
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode
ParseMode = ParseMode.HTML

from engine.orchestrator import ConsensusOrchestrator
from memory.shared_context import SharedMemory
from memory.blackboard import Blackboard

# Config
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
CONSENSUS_CONFIG = os.environ.get("CONSENSUS_CONFIG", "config.yaml")
SENTINEL_ROOT = os.environ.get("SENTINEL_OMEGA_ROOT", "/home/deamon/workspaces/sentinel_omega")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Global state ──────────────────────────────────────────────
orchestrator: Optional[ConsensusOrchestrator] = None
shared_memory: Optional[SharedMemory] = None
active_jobs: Dict[int, Dict] = {}  # chat_id -> {task_id, blackboard, status}


# ─── Helpers ───────────────────────────────────────────────────
def format_blackboard(bb: Blackboard) -> str:
    """Format blackboard for Telegram (HTML, < 4096 chars)."""
    import html
    consensus_score = html.escape(str(bb.consensus_score))
    task_id = html.escape(bb.task_id)
    rounds = html.escape(str(bb.refinement_rounds))
    status = "✅ Consenso" if bb.consensus_reached else "⚠️ Límite rondas"
    synthesis = html.escape(bb.final_synthesis[:3500])
    
    lines = [
        f"🧠 <b>Consenso Final</b> (Score: <code>{consensus_score}</code>/100)",
        f"🆔 Task: <code>{task_id}</code> | {status}",
        f"🔄 Rondas refinamiento: <code>{rounds}</code>",
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
    """Format execution timeline."""
    import html
    if not bb.execution_timeline:
        return "<i>(sin eventos)</i>"
    lines = ["📋 <b>Timeline de ejecución:</b>"]
    for ev in bb.execution_timeline[-8:]:
        icon = {"RESEARCH": "🔍", "CODING": "💻", "REVIEW": "⚖️", "REFINING": "🛠️", "SYNTHESIS": "✨"}.get(ev.get("stage"), "🤖")
        agent = html.escape(ev.get('agent', '?'))
        message = html.escape(ev.get('message', '')[:120])
        lines.append(f"{icon} <b>{agent}</b> — {message}")
    return "\n".join(lines)


def sentinel_health() -> str:
    """Read-only Sentinel Omega status."""
    import html
    root = Path(SENTINEL_ROOT)
    db = root / "data" / "SENTINEL_OMEGA_PRO.db"
    log = root / "data" / "sentinel_omega.log"
    
    if not db.exists():
        return "🔴 <b>Sentinel Omega</b>: DB no encontrada"
    
    import sqlite3
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.execute("SELECT MAX(timestamp), COUNT(*) FROM TBL_CICLOS")
        last_ciclo, total = cur.fetchone()
        cur = conn.execute("SELECT MAX(timestamp), COUNT(*) FROM TBL_PRECURSORES_COSMICOS")
        last_prec, prec_total = cur.fetchone()
        cur = conn.execute("SELECT MAX(timestamp), COUNT(*) FROM TBL_JUEZ_AUDITORIA")
        last_juez, juez_total = cur.fetchone()
        conn.close()
        
        from datetime import datetime
        last_str = datetime.fromtimestamp(last_ciclo).strftime("%d/%m %H:%M") if last_ciclo else "N/A"
        return (
            f"🟢 <b>Sentinel Omega</b> — Online\n"
            f"📊 Ciclos: <code>{total}</code> (último: {html.escape(last_str)})\n"
            f"🛰️ Precursores: <code>{prec_total}</code>\n"
            f"⚖️ Auditorías Juez: <code>{juez_total}</code>\n"
            f"💾 DB: <code>{html.escape(db.name)}</code>"
        )
    except Exception as e:
        return f"🟡 <b>Sentinel Omega</b>: Error leyendo BD — {html.escape(str(e))}"


# ─── Keyboards ─────────────────────────────────────────────────
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Nueva tarea al Concilio", callback_data="new_task")],
        [InlineKeyboardButton("🔍 Auditoría Sentinel Omega", callback_data="audit_sentinel")],
        [InlineKeyboardButton("📊 Estado Sentinel", callback_data="sentinel_status")],
        [InlineKeyboardButton("📜 Ver Blackboard activo", callback_data="show_blackboard")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="help")],
    ])


def audit_focus_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔬 Completa", callback_data="audit_full")],
        [InlineKeyboardButton("🧪 Tests", callback_data="audit_tests")],
        [InlineKeyboardButton("🔐 Secretos/Seguridad", callback_data="audit_secrets")],
        [InlineKeyboardButton("📦 Migraciones/DB", callback_data="audit_migrations")],
        [InlineKeyboardButton("⚙️ Automatización/CI", callback_data="audit_automation")],
        [InlineKeyboardButton("🔙 Volver", callback_data="back_main")],
    ])


# ─── Handlers ──────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🧠 <b>Consenso de Expertos + Sentinel Omega</b>\n\n"
        "Bienvenido. El Concilio (Nemotron → DeepSeek → Gemma) está listo.\n"
        "Sentinel Omega está corriendo en background.\n\n"
        "¿Qué deseas hacer?",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "<b>Comandos disponibles:</b>\n"
        "/start — Menú principal\n"
        "/task <prompt> — Enviar tarea directa al Concilio\n"
        "/audit [foco] — Auditar Sentinel (foco: tests, secrets, migrations, automation)\n"
        "/status — Estado rápido de Sentinel\n"
        "/blackboard — Ver pizarra activa\n"
        "/cancel — Cancelar tarea en curso\n\n"
        "<b>Ejemplos:</b>\n"
        "<code>/task Crea un scraper async con reintentos</code>\n"
        "<code>/audit tests</code>\n"
        "<code>/audit security</code>",
        parse_mode=ParseMode
    )


async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    prompt = " ".join(context.args).strip()
    if not prompt:
        await update.message.reply_text("Uso: <code>/task <tu prompt></code>", parse_mode=ParseMode)
        return
    await run_consensus_task(update, prompt)


async def audit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    focus = " ".join(context.args).strip() or ""
    await run_audit(update, focus)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    msg = sentinel_health()
    await update.message.reply_text(msg, parse_mode=ParseMode)


async def blackboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    if shared_memory and shared_memory.active_blackboard:
        bb = shared_memory.active_blackboard
        await update.message.reply_text(
            format_blackboard(bb) + "\n\n" + format_timeline(bb),
            parse_mode=ParseMode
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
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "new_task":
        await query.edit_message_text(
            "📝 Envía tu prompt como mensaje de texto.\nEjemplo: <code>Crea una API REST con FastAPI y autenticación JWT</code>",
            parse_mode=ParseMode
        )
        context.user_data["awaiting_task"] = True

    elif data == "audit_sentinel":
        await query.edit_message_text(
            "🔍 <b>Auditoría Sentinel Omega</b>\nSelecciona foco:",
            reply_markup=audit_focus_keyboard(),
            parse_mode=ParseMode
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
        await run_audit(query, focus, edit=True)

    elif data == "sentinel_status":
        msg = sentinel_health()
        await query.edit_message_text(msg, reply_markup=main_keyboard(), parse_mode=ParseMode)

    elif data == "show_blackboard":
        if shared_memory and shared_memory.active_blackboard:
            bb = shared_memory.active_blackboard
            await query.edit_message_text(
                format_blackboard(bb) + "\n\n" + format_timeline(bb),
                reply_markup=main_keyboard(),
                parse_mode=ParseMode
            )
        else:
            await query.edit_message_text("No hay blackboard activa.", reply_markup=main_keyboard())

    elif data == "help":
        await query.edit_message_text(
            "<b>Comandos:</b>\n"
            "/task <prompt> — Tarea directa\n"
            "/audit [foco] — Auditoría\n"
            "/status — Estado Sentinel\n"
            "/blackboard — Ver pizarra\n"
            "/cancel — Cancelar",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode
        )

    elif data == "back_main":
        await query.edit_message_text(
            "🧠 <b>Menú principal</b>",
            reply_markup=main_keyboard(),
            parse_mode=ParseMode
        )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    logger.info(f"Received message from {update.effective_chat.id}: {update.message.text[:50] if update.message.text else 'no text'}")
    if context.user_data.get("awaiting_task"):
        context.user_data["awaiting_task"] = False
        prompt = update.message.text.strip()
        if prompt:
            await run_consensus_task(update, prompt)
    else:
        await update.message.reply_text(
            "Usa /task <prompt> o el menú /start",
            reply_markup=main_keyboard()
        )


# ─── Core execution ────────────────────────────────────────────
async def run_consensus_task(update: Update, prompt: str, edit: bool = False):
    # Handle both Update (from command/message) and CallbackQuery
    if hasattr(update, 'callback_query') and update.callback_query:
        chat_id = update.callback_query.message.chat.id
    elif hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id = update.effective_chat.id
    elif hasattr(update, 'message') and update.message:
        chat_id = update.message.chat.id
    else:
        logger.error("Cannot determine chat_id from update")
        return
    
    if chat_id in active_jobs:
        msg = "⚠️ Ya hay una tarea en curso. Usa /cancel para cancelarla."
        if edit:
            await update.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    # Get bot and proper edit/send method based on update type
    if hasattr(update, 'callback_query') and update.callback_query:
        bot = update.callback_query.bot
        status_msg = await bot.send_message(
            chat_id=chat_id,
            text="🔄 <b>Iniciando Concilio...</b>\n🔍 Nemotron investigando...\n💻 DeepSeek codificando...\n⚖️ Gemma auditando...",
            parse_mode=ParseMode
        )
    else:
        status_msg = await (update.edit_message_text if edit else update.message.reply_text)(
            "🔄 <b>Iniciando Concilio...</b>\n🔍 Nemotron investigando...\n💻 DeepSeek codificando...\n⚖️ Gemma auditando...",
            parse_mode=ParseMode
        )

    active_jobs[chat_id] = {"started": datetime.now(timezone.utc), "prompt": prompt}

    try:
        # Run in thread pool to not block bot
        loop = asyncio.get_event_loop()
        bb = await loop.run_in_executor(
            None,
            lambda: orchestrator.run_consensus(
                user_prompt=prompt,
                shared_memory=shared_memory
            )
        )

        active_jobs.pop(chat_id, None)

        text = format_blackboard(bb) + "\n\n" + format_timeline(bb)
        await status_msg.edit_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode)

    except Exception as e:
        active_jobs.pop(chat_id, None)
        logger.exception("Consensus task failed")
        await status_msg.edit_text(f"❌ Error: {e}", reply_markup=main_keyboard())


async def run_audit(update: Update, focus: str, edit: bool = False):
    """Run Sentinel audit via Consensus Orchestrator."""
    # Handle both Update (from command) and CallbackQuery (from button)
    if hasattr(update, 'callback_query') and update.callback_query:
        chat_id = update.callback_query.message.chat.id
    elif hasattr(update, 'effective_chat') and update.effective_chat:
        chat_id = update.effective_chat.id
    elif hasattr(update, 'message') and update.message:
        chat_id = update.message.chat.id
    else:
        logger.error("Cannot determine chat_id from update")
        return

    if chat_id in active_jobs:
        msg = "⚠️ Ya hay una tarea en curso."
        if edit:
            await update.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        return

    # Get bot and proper edit/send method based on update type
    if hasattr(update, 'callback_query') and update.callback_query:
        bot = update.callback_query.bot
        status_msg = await bot.send_message(
            chat_id=chat_id,
            text=f"🔍 <b>Auditoría Sentinel Omega</b> {'(' + focus + ')' if focus else '(completa)'}\n"
            "🔍 Nemotron analizando arquitectura...\n"
            "💻 DeepSeek revisando código...\n"
            "⚖️ Gemma evaluando...\n",
            parse_mode=ParseMode
        )
    else:
        status_msg = await (update.edit_message_text if edit else update.message.reply_text)(
            f"🔍 <b>Auditoría Sentinel Omega</b> {'(' + focus + ')' if focus else '(completa)'}\n"
            "🔍 Nemotron analizando arquitectura...\n"
            "💻 DeepSeek revisando código...\n"
            "⚖️ Gemma evaluando...\n",
            parse_mode=ParseMode
        )

    active_jobs[chat_id] = {"started": datetime.now(timezone.utc), "audit": focus}

    try:
        loop = asyncio.get_event_loop()
        bb = await loop.run_in_executor(
            None,
            lambda: orchestrator.audit_project(focus=focus)
        )

        active_jobs.pop(chat_id, None)

        text = format_blackboard(bb) + "\n\n" + format_timeline(bb)
        await status_msg.edit_text(text, reply_markup=main_keyboard(), parse_mode=ParseMode)

    except Exception as e:
        active_jobs.pop(chat_id, None)
        logger.exception("Audit failed")
        await status_msg.edit_text(f"❌ Error en auditoría: {e}", reply_markup=main_keyboard())


def is_authorized(update: Update) -> bool:
    """Check if user is authorized (by chat_id)."""
    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID not set — allowing all (dev mode)")
        return True
    chat_id = str(update.effective_chat.id)
    authorized = chat_id == TELEGRAM_CHAT_ID or chat_id in TELEGRAM_CHAT_ID.split(",")
    if not authorized:
        logger.warning(f"Unauthorized access attempt: {chat_id}")
        if update.message:
            asyncio.create_task(update.message.reply_text("🚫 No autorizado"))
        elif update.callback_query:
            asyncio.create_task(update.callback_query.answer("🚫 No autorizado", show_alert=True))
    return authorized


# ─── Main ──────────────────────────────────────────────────────
def main():
    global orchestrator, shared_memory

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado en entorno")

    logger.info("Inicializando Consensus Orchestrator...")
    orchestrator = ConsensusOrchestrator(config_path=CONSENSUS_CONFIG)
    shared_memory = SharedMemory(db_path=orchestrator.db_path)
    logger.info("✅ Orchestrator listo")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("audit", audit_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("blackboard", blackboard_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    # Callbacks & messages
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    logger.info("🤖 Bot iniciado — polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()