# Changelog - Consensus Expert Agent + Sentinel Omega

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-09-01

### Added - Telegram Bot Integration
- **Bidirectional Telegram integration** between Sentinel Omega and Consensus Expert Agent
- **Sentinel Omega → Telegram**: `infrastructure/api/telegram.py` with `send_alert()` for real-time precursor alerts
- **Consensus Expert Agent Bot** (`telegram_bot.py`): Full-featured Telegram bot with:
  - `/start` — Main menu with inline keyboard
  - `/task <prompt>` — Submit task to Concilio (Nemotron → DeepSeek → Gemma)
  - `/audit [focus]` — Audit Sentinel Omega (tests, secrets, migrations, automation)
  - `/status` — Real-time Sentinel Omega status (cycles, precursors, judge audits)
  - `/blackboard` — View active consensus blackboard
  - `/cancel` — Cancel running task
  - Inline callback buttons for all actions
- **Shared credentials**: Single `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in both `.env` files
- **Sentinel Omega DB integration**: Consensus bot reads live data from `SENTINEL_OMEGA_PRO.db`
- **HTML parse mode** for rich Telegram formatting (bold, code, inline)

### Fixed - Sentinel Omega Package Structure
- Created `sentinel_omega/__init__.py` to fix `ModuleNotFoundError: No module named 'sentinel_omega'`
- Fixed `pyproject.toml` package find config (`include = ["sentinel_omega*"]`)
- Reinstalled editable with `--break-system-packages` for system Python 3.13 compatibility

### Fixed - Consensus Bot Issues
- Fixed `Blackboard` import: `from memory.blackboard import Blackboard`
- Installed `python-telegram-bot>=21.0` and `python-dotenv` in venv
- Fixed `CallbackQuery` attribute error: `chat_id = update.effective_chat.id if update.effective_chat else update.callback_query.message.chat.id`
- Switched from Markdown to HTML parse mode to avoid Telegram parsing errors

### Infrastructure
- Created `run_telegram_bot.sh` launcher script with venv activation
- Created `.env.example` template for credentials
- Created `TELEGRAM_BOT_README.md` comprehensive documentation

### Verified Working (2026-09-02)
- **Bot running as daemon**: Background process polling Telegram API (`getUpdates` every 10s)
- **Concilio fully operational**: Nemotron → DeepSeek → Gemma sequential calls via Ollama (localhost:11434)
- **Real task execution logged**: User "Puedes revisar la seguridad" → 4 Ollama calls → final synthesis delivered via `editMessageText`
- **Sentinel DB reads working**: `/status` returns live data (10,651 cycles, 1,418 alerts, 29,270 predictions, 897,356 judge events)
- **Dashboard accessible**: Streamlit on port 8502 (port 8501 occupied by Docker), binding 0.0.0.0 for LAN access (http://192.168.1.144:8502)

## [2.0.0] - 2026-08-XX

### Added - Core Consensus System
- Multi-model consensus engine (Nemotron/DeepSeek/Gemma via Ollama)
- Shared memory blackboard architecture (SQLite)
- Iterative refinement protocol with consensus scoring (0-100)
- Web dashboard (FastAPI + vanilla JS)
- CLI interactive mode

### Added - Sentinel Omega Integration
- Precursor detection platform with 15-type scanner
- 5-wall cross-correlation engine
- 125-node topology analysis
- Schumann harmonic filter (TITAN V32/V46/V53 lineage)
- SQLite persistence: `SENTINEL_OMEGA_PRO.db`

## [1.0.0] - 2026-08-XX

### Added - Initial Release
- Basic consensus orchestrator
- Memory management
- Configuration system