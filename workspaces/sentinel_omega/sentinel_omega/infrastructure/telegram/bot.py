"""
Unified Telegram Bot — thin wrapper over infrastructure.api.telegram
"""

import logging
from dataclasses import dataclass

from sentinel_omega.infrastructure.api import telegram as tg

logger = logging.getLogger(__name__)


@dataclass
class TelegramMessage:
    layer: str
    signal_type: str
    confidence: float
    summary: str
    details: str = ""


class SentinelTelegramBot:
    LAYER_EMOJIS = {"geodynamic": "🌍", "system": "⚙️", "omega": "Ω"}

    def __init__(self, token: str = "", chat_id: str = ""):
        import os
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self._enabled = bool(self._token and self._chat_id)

    def send_alert(self, msg: TelegramMessage) -> bool:
        emoji = self.LAYER_EMOJIS.get(msg.layer, "⚡")
        text = (
            f"{emoji} <b>SENTINEL OMEGA — {msg.layer.upper()}</b>\n"
            f"Signal: {msg.signal_type} ({msg.confidence:.0%})\n"
            f"{msg.summary}\n"
        )
        if msg.details:
            text += f"\n{msg.details}"
        # Always ingest via the Padre watcher (hourly digest / unprecedented-only).
        # No token still "succeeds" as dry ingest — never hits Telegram here.
        try:
            from sentinel_omega.infrastructure.messaging.alert_service import (
                FormattedMessage, Severity, AlertService,
            )
            fm = FormattedMessage(
                html=text, markdown=text, plain=text,
                subject=f"[SENTINEL] {msg.layer}_{msg.signal_type}",
                severity=Severity.AMARILLO if msg.signal_type.lower() in ("alert", "watch") else Severity.AZUL,
                alert_type=f"{msg.layer}_{msg.signal_type}".upper(),
            )
            out = AlertService(dry_run=not self._enabled).dispatch(fm, channels=["telegram", "log"])
            return bool(out.get("telegram"))
        except Exception:
            if not self._enabled:
                logger.info(f"[DRY RUN] Telegram: {text}")
                return True
            return tg.send_alert_gated(text, f"{msg.layer}_{msg.signal_type}")

    def send_heartbeat(self, status: dict) -> bool:
        layers_status = " | ".join(
            f"{'✅' if v else '❌'} {k}" for k, v in status.items()
        )
        try:
            from sentinel_omega.infrastructure.messaging.alert_service import (
                AlertService, AlertTemplates,
            )
            out = AlertService(dry_run=not self._enabled).dispatch(
                AlertTemplates.heartbeat(f"Layers: {layers_status}"),
                channels=["telegram", "log"],
            )
            return bool(out.get("telegram"))
        except Exception:
            if not self._enabled:
                logger.info(f"[DRY RUN] Telegram Heartbeat: Layers: {layers_status}")
                return True
            return tg.maybe_heartbeat(f"Layers: {layers_status}")
