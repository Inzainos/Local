"""Carga config.yaml + .env y expone un objeto de configuracion unico."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


class Config:
    def __init__(self, raw: dict):
        self._raw = raw

    def __getitem__(self, key):
        return self._raw[key]

    def get(self, *keys, default=None):
        node = self._raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def api_keys(self):
        return {
            "virustotal": os.environ.get("VT_API_KEY") or None,
            "otx": os.environ.get("OTX_API_KEY") or None,
            "abuseipdb": os.environ.get("ABUSEIPDB_API_KEY") or None,
            "openrouter": os.environ.get("OPENROUTER_API_KEY") or None,
            "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN") or None,
            "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID") or None,
        }


def load_config() -> Config:
    with open(CONFIG_PATH, "r") as f:
        raw = yaml.safe_load(f)
    return Config(raw)


def ensure_dirs(cfg: Config):
    for key in ("data_dir", "quarantine_dir", "forensics_dir", "baseline_dir", "log_dir"):
        Path(cfg.get("paths", key)).mkdir(parents=True, exist_ok=True)
