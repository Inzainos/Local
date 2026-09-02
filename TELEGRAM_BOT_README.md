# 🤖 Telegram Bot — Consensus Expert Agent + Sentinel Omega Bridge

Bot de Telegram que integra el **Concilio de Expertos** (Nemotron → DeepSeek → Gemma) con **Sentinel Omega**, permitiendo consultar tareas, auditorías y recibir reportes consensuados desde Telegram.

## ✨ Características

| Función | Descripción |
|---------|-------------|
| `/task <prompt>` | Envía una tarea directa al Concilio (Investigación → Código → Consenso) |
| `/audit [foco]` | Auditoría completa de Sentinel Omega (focos: tests, secrets, migrations, automation) |
| `/status` | Estado en vivo de Sentinel Omega (ciclos, precursores, Juez, DB) |
| `/blackboard` | Ver la pizarra activa del último consenso |
| Menú interactivo | Botones inline para navegar sin escribir comandos |

## 🚀 Inicio Rápido

### 1. Configurar variables de entorno

```bash
cd /home/deamon/consensus-expert-agent
cp .env.example .env
# Edita .env con tu TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
```

### 2. Obtener credenciales de Telegram

1. Habla con **@BotFather** → `/newbot` → obtén `TELEGRAM_BOT_TOKEN`
2. Habla con **@userinfobot** → obtén tu `TELEGRAM_CHAT_ID` (numérico)
3. (Opcional) Para múltiples usuarios, separa chat_ids con coma: `123456789,987654321`

### 3. Ejecutar

```bash
# Opción A: Script launcher
chmod +x run_telegram_bot.sh
./run_telegram_bot.sh

# Opción B: Directo con venv
source .venv/bin/activate
python telegram_bot.py
```

## 📋 Comandos y Uso

### Menú principal (`/start`)
```
🧠 Consenso de Expertos + Sentinel Omega

[🧠 Nueva tarea al Concilio]
[🔍 Auditoría Sentinel Omega]
[📊 Estado Sentinel]
[📜 Ver Blackboard activo]
[❓ Ayuda]
```

### Tarea directa
```
/task Crea una API REST con FastAPI, autenticación JWT y rate limiting
```

### Auditoría con foco
```
/audit              # Auditoría completa
/audit tests        # Solo tests
/audit security     # Secretos y seguridad
/audit migrations   # Migraciones de BD
/audit automation   # CI/CD y automatización
```

### Estado Sentinel
```
/status
```
Respuesta ejemplo:
```
🟢 Sentinel Omega — Online
📊 Ciclos: `10,685` (último: 01/09 22:11)
🛰️ Precursores: `8,470`
⚖️ Auditorías Juez: `897,420`
💾 DB: `SENTINEL_OMEGA_PRO.db`
```

## 🏗️ Arquitectura del Bot

```
┌─────────────────────────────────────────────────────────────┐
│                    TELEGRAM USER                            │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS (Bot API)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  TELEGRAM BOT (python-telegram-bot)         │
│  • Handlers: /start, /task, /audit, /status, /blackboard   │
│  • Callbacks: Menús inline, selección de foco auditoría    │
│  • Auth: Validación TELEGRAM_CHAT_ID                        │
└─────────────────────────┬───────────────────────────────────┘
                          │ asyncio.run_in_executor (ThreadPool)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              CONSENSUS ORCHESTRATOR (Ollama)                │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Nemotron    │───▶│  DeepSeek    │───▶│  Gemma       │  │
│  │  Researcher  │    │  Coder       │    │  Optimizer   │  │
│  │  (qwen2.5)   │    │  (qwen2.5)   │    │  (gemma4)    │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           SHARED MEMORY (SQLite Blackboard)          │  │
│  │  • Research findings  • Code proposals  • Critiques  │  │
│  │  • Refinement history • Final synthesis • Timeline   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼ (Read-only)
┌─────────────────────────────────────────────────────────────┐
│                    SENTINEL OMEGA (SQLite)                  │
│  • TBL_CICLOS, TBL_PRECURSORES_COSMICOS, TBL_JUEZ_AUDITORIA│
└─────────────────────────────────────────────────────────────┘
```

## ⚙️ Configuración Avanzada

### Variables de entorno

| Variable | Requerida | Default | Descripción |
|----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Token de @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | — | Chat ID(s) autorizado(s) |
| `CONSENSUS_CONFIG` | ❌ | `config.yaml` | Path a config del Concilio |
| `SENTINEL_OMEGA_ROOT` | ❌ | `/home/deamon/workspaces/sentinel_omega` | Raíz Sentinel para `/status` |

### Modelos Ollama (en `config.yaml`)

```yaml
roles:
  researcher:
    model: "qwen2.5:1.5b"      # Investigación rápida
  coder:
    model: "qwen2.5:1.5b"      # Código eficiente
  optimizer:
    model: "gemma4:26b"        # Consenso profundo (requiere más RAM)
```

> **Nota**: `gemma4:26b` usa ~16GB RAM. Para menos recursos, cambia a `gemma2:2b` o `qwen2.5:1.5b`.

## 🔐 Seguridad

- **Solo chat_ids autorizados** pueden usar el bot (validación en `is_authorized()`)
- **Modo solo lectura** para Sentinel Omega: el bot NUNCA inicia/modifica Sentinel, solo consulta BD
- **Credenciales solo por entorno**: nunca hardcodeadas
- **Timeouts**: 120s por modelo (configurable en `config.yaml`)

## 📊 Flujo de una Tarea

```
Usuario: /task "Crea un scraper async con reintentos"
                    │
                    ▼
         ┌─────────────────────┐
         │  Nemotron (Research)│  ← Analiza requisitos, busca mejores librerías
         │  - Async patterns   │
         │  - Retry strategies │
         │  - Edge cases       │
         └──────────┬──────────┘
                    │ Blackboard: research.raw_content
                    ▼
         ┌─────────────────────┐
         │  DeepSeek (Coding)  │  ← Escribe código tipado, modular, con tests
         │  - aiohttp + tenacity│
         │  - Typed, documented │
         └──────────┬──────────┘
                    │ Blackboard: code_proposal
                    ▼
         ┌─────────────────────┐
         │  Gemma (Review)     │  ← Audita: performance, seguridad, reglas duras
         │  Score: 92/100 ✅   │
         └──────────┬──────────┘
                    │ Consenso ≥ 85 → Síntesis final
                    ▼
         ┌─────────────────────┐
         │  RESPUESTA FINAL    │  ← Markdown con código + explicación + score
         └─────────────────────┘
```

## 🛠️ Desarrollo / Extensión

### Añadir nuevo comando

```python
# En telegram_bot.py
async def mi_comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update): return
    await update.message.reply_text("Mi respuesta")

# Registrar en main():
app.add_handler(CommandHandler("mi_comando", mi_comando))
```

### Añadir nuevo foco de auditoría

1. En `audit_focus_keyboard()`: añade botón
2. En `on_callback()`: mapea `audit_nuevo` → foco string
3. El `orchestrator.audit_project(focus="nuevo")` lo recibe en el prompt base

### Personalizar formato de respuesta

Modifica `format_blackboard()` y `format_timeline()` en `telegram_bot.py`.

## 🐛 Troubleshooting

| Problema | Solución |
|----------|----------|
| `ModuleNotFoundError: python-telegram-bot` | `pip install python-telegram-bot>=21.0` en venv |
| `TELEGRAM_BOT_TOKEN no configurado` | Revisa `.env` o exporta variable |
| `Unauthorized` | Verifica `TELEGRAM_CHAT_ID` coincide con tu chat |
| Timeout en tareas | Aumenta `timeout_seconds` en `config.yaml` |
| Ollama no responde | `ollama serve` y verifica `ollama list` tiene modelos |
| Memoria alta (gemma4:26b) | Cambia optimizer a `gemma2:2b` o `qwen2.5:1.5b` |

## 📝 Logs

El bot loggea a stdout con formato:
```
2026-09-01 16:30:45 | INFO     | __main__: 🤖 Bot iniciado — polling...
2026-09-01 16:31:02 | INFO     | __main__: Consensus task completed for chat 123456789
```

Para debug: `export LOG_LEVEL=DEBUG` antes de ejecutar.

## 🔗 Integración con Sentinel Omega

El bot comparte la misma BD de memoria (`data/shared_memory.db`) y puede:
- Consultar estado de Sentinel (`/status`)
- Auditar código de Sentinel (`/audit`)
- Recibir alertas de Sentinel (configura `TELEGRAM_BOT_TOKEN`/`CHAT_ID` en Sentinel y usa `infrastructure.api.telegram`)

---

**¿Preguntas?** Abre un issue o consulta la documentación del [Consensus Expert Agent](../README.md) y [Sentinel Omega](../../sentinel_omega/CLAUDE.md).