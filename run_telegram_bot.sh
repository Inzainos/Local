#!/usr/bin/env bash
# Launch script for Telegram Bot with Consensus Expert Agent
set -euo pipefail
cd /home/deamon/consensus-expert-agent

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"
export CONSENSUS_CONFIG="${CONSENSUS_CONFIG:-config.yaml}"
export SENTINEL_OMEGA_ROOT="${SENTINEL_OMEGA_ROOT:-/home/deamon/workspaces/sentinel_omega}"

if [[ -z "${TELEGRAM_BOT_TOKEN}" ]]; then
  echo "ERROR: TELEGRAM_BOT_TOKEN no configurado (.env o entorno)" >&2
  exit 1
fi

source .venv/bin/activate
exec python telegram_bot.py
