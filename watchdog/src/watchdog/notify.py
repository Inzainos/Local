"""Logging a archivo + notificacion opcional por Telegram."""
import logging
import sys
from pathlib import Path

import requests


def get_logger(cfg) -> logging.Logger:
    log_dir = Path(cfg.get("paths", "log_dir"))
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("watchdog")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")

    fh = logging.FileHandler(log_dir / "watchdog.log")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def telegram_notify(cfg, message: str):
    if not cfg.get("notify", "telegram_enabled", default=False):
        return
    keys = cfg.api_keys
    token, chat_id = keys["telegram_bot_token"], keys["telegram_chat_id"]
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message[:4000]},
            timeout=10,
        )
    except requests.RequestException:
        pass
