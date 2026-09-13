# Telegram Bot — Consensus Expert Agent + Sentinel Omega Bridge

Bot de Telegram que integra el **Concilio** (pipeline secuencial worker → árbitro, umbral **85**) con **Sentinel Omega** (estado read-only + cola de alertas).

## Politica de alertas (no romper)

| Canal | Regla |
|-------|-------|
| Digest horario | **Siempre** (aunque esté calmado) — Sentinel Padre / consenso_vigilante |
| Telegram inmediato | Solo eventos **sin precedentes** |
| Este bot (Consensus) | /task, /audit, /status, /reporte + entrega de alert_queue |

Si Sentinel encola en data/alert_queue.json, el poller del bot envía a TELEGRAM_CHAT_ID.

## Caracteristicas

| Funcion | Descripcion |
|---------|-------------|
| /task <prompt> | Tarea al Concilio secuencial |
| /audit [foco] | Auditoria Sentinel via orquestador |
| /status | Concilio health + cola + ultima .concilio + Ollama + Sentinel |
| /reporte | Igual que status + politica + links (alias /report) |
| /queue | alert_queue.get_stats() |
| /blackboard | Pizarra activa |
| Mini App | Boton WebApp si TELEGRAM_WEBAPP_URL es **HTTPS** publico |

## Inicio rapido

`ash
cd /home/deamon/consensus-expert-agent
cp .env.example .env   # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# Opcional:
# TELEGRAM_WEBAPP_URL=https://tu-dominio/mini
# CONSENSUS_DASHBOARD_URL=http://127.0.0.1:8000
./run_telegram_bot.sh
`

### Mini App

`ash
source .venv/bin/activate
python main.py --web --port 8000
# Abrir http://127.0.0.1:8000/mini
# API:  http://127.0.0.1:8000/api/mini/status
# Alt:  /api/concilio/health  /api/alerts/stats  /static/mini.html
`

Telegram **exige HTTPS publico** para WebApp. Expo /mini con tunel/reverse-proxy y setea TELEGRAM_WEBAPP_URL. Sin HTTPS el boton no se muestra (localhost se omite a proposito).

## Variables de entorno

| Variable | Requerida | Descripcion |
|----------|-----------|-------------|
| TELEGRAM_BOT_TOKEN | si | Token @BotFather |
| TELEGRAM_CHAT_ID | si | Chat ID(s) autorizados |
| CONSENSUS_CONFIG | no | Default config.yaml |
| SENTINEL_OMEGA_ROOT | no | Bloque Sentinel en /status |
| TELEGRAM_WEBAPP_URL | no | HTTPS publico → boton Mini App |
| CONSENSUS_DASHBOARD_URL | no | Link en reporte/miniapp |

## Menu

`
[Nueva tarea al Concilio]
[Auditoria Sentinel Omega]
[Estado / Reporte] [Cola]
[Ver Blackboard activo]
[Mini App]   ← solo si TELEGRAM_WEBAPP_URL=https://…
[Ayuda]
`

## Seguridad

- Solo chat_ids autorizados (is_authorized, callbacks incluidos)
- Sentinel **solo lectura**
- Credenciales solo por env — nunca en respuestas ni miniapp JSON
- .concilio = DATA (anti-inyeccion)

## Relacionado

- README.md · AGENTS.md · CONCILIO.md
- Handoff: docs/HANDOFF_GEMMA_MEMORIA.md
- Sentinel Dev: infrastructure/messaging/consenso_vigilante.py
