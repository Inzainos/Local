#!/usr/bin/env bash
# Launch script for Telegram Bot with Consensus Expert Agent

cd /home/deamon/consensus-expert-agent

# Load environment variables
export TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
export TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID}"
export CONSENSUS_CONFIG="${CONSENSUS_CONFIG:-config.yaml}"
export SENTINEL_OMEGA_ROOT="${SENTINEL_OMEGA_ROOT:-/home/deamon/workspaces/sentinel_omega}"

# Activate venv and run
source .venv/bin/activate
python telegram_bot.py