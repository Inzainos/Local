# Funcionamiento — Bot Telegram + Mini App (Consensus / Concilio)

Version documentada: **2.2.5** (2026-09-13)
Codigo: `telegram_bot.py`, `alert_queue.py`, `web_ui.py`, `static/mini.html`
Docs hermanas: `TELEGRAM_BOT_README.md`, `CONCILIO.md`, `docs/HANDOFF_GEMMA_MEMORIA.md`

---

## Que es

El bot es el frente humano del proyecto `consensus-expert-agent`:

1. `/task` = respuesta **ligera** (Ollama worker + pack Sentinel); `/concilio` = Concilio completo.
2. Te muestra **estado / reportes** sin secretos.
3. Entrega alertas que Sentinel deja en una **cola** (`data/alert_queue.json`).
4. Opcionalmente abre una **Mini App** (WebApp de Telegram) con las mismas tarjetas de estado.

No sustituye a Sentinel Omega: Sentinel sigue siendo el sistema de precursores. Este bot es el puente Consensus a Telegram.

---

## Diagrama de flujo

```
Tu en Telegram
    |
    |  /task  /audit  /status  /reporte  botones
    v
telegram_bot.py  (solo chat_ids autorizados)
    |
    +---> /task  -> fast_ask (ligero + pack Sentinel thin)
    |         eventos/precursores -> DB Sentinel (no LLM inventando)
    |
    +---> /concilio|/audit -> ConsensusOrchestrator (Concilio secuencial)
    |         lightest -> medium -> heavy(Gemma) -> light verify
    |         /audit: inject_sentinel temporal; /concilio: config inject=false
    |         escribe data/sessions/<id>.concilio
    |         unload Ollama entre roles
    |
    +---> alert_queue.py  (poller)
    |         lee data/alert_queue.json
    |         envia a TELEGRAM_CHAT_ID; requeue si falla
    |
    +---> web_ui --port 8002 (consensus-web.service)
              /mini  +  /api/mini/status
```

Sentinel (otro proceso) puede encolar alertas. La politica Sentinel es:

| Tipo | Cuando sale a Telegram |
|------|-------------------------|
| Digest horario | Siempre (aunque este calmado) |
| Alerta inmediata | Solo eventos sin precedentes |

Este bot Consensus no redefine esa politica: entrega lo que llega a la cola + tus comandos /task.

---

## Comandos

| Comando | Que hace |
|---------|----------|
| `/start` | Menu: Nueva tarea, Auditoria, Estado/Reporte, Cola, Blackboard, Mini App (si HTTPS), Ayuda |
| `/task <prompt>` | Respuesta **ligera** (`fast_ask` + pack Sentinel). Eventos/precursores → DB real |
| `/concilio <prompt>` | Concilio **completo** (heavy, umbral 85, sesiones `.concilio`) |
| `/audit [foco]` | Auditoria Concilio con **inject Sentinel temporal** (tests/secretos/DB/CI) |
| `/status` | Health Concilio: umbral 85, sequential, tags worker/arbitro, N sesiones, ultima sesion, Ollama cargados, cola, Sentinel RO |
| `/reporte` o `/report` | Como status + politica de alertas + links |
| `/queue` | Solo stats de la cola |
| `/blackboard` | Pizarra activa |
| `/cancel` | Cancela job en mapa |

---

## Concilio por dentro (cuando usas /concilio o /audit)

1. Ligero (qwen / concilio-worker) investiga, escribe `.concilio`, se descarga.
2. Mediano (coder) implementa/refina, escribe, se descarga.
3. Pesado (Gemma / concilio-arbitro) puntua `[PUNTUACION_CONSENSO: XX]`, se descarga.
4. Ligero vuelve a leer el `.concilio` y verifica el porcentaje.
5. Si queda bajo 85, otra vuelta completa hasta max rondas (default 3).

Anti-inyeccion: el contenido del `.concilio` y del usuario se cerca como DATA, no como ordenes al system de Gemma.

Preguntas rapidas de Telegram `/task` y dashboard van por `fast_ask` (ligero). Eventos Sentinel en Telegram leen DB via `sentinel_proximos_eventos`.

---

## Mini App

1. UI via `consensus-web.service` o `python main.py --web --port 8002`
2. Local: `http://127.0.0.1:8002/mini` y JSON `/api/mini/status`
3. Para el boton dentro de Telegram necesitas URL HTTPS publica en `.env`: `TELEGRAM_WEBAPP_URL=https://tu-dominio/mini`
4. Sin HTTPS el boton no se muestra (localhost se ignora a proposito).

---

## Arranque

```bash
cd /home/deamon/consensus-expert-agent
cp -n .env.example .env
# Preferido en host: units systemd
#   systemctl status consensus-telegram.service consensus-web.service
# Manual:
source .venv/bin/activate
./run_telegram_bot.sh
# otra terminal:
python main.py --web --port 8002
```

Variables: ver tabla en `TELEGRAM_BOT_README.md`.

---

## Seguridad

- Solo TELEGRAM_CHAT_ID autorizados.
- Sentinel solo lectura desde el bot.
- Tokens solo en env; nunca en respuestas ni JSON de miniapp.
- No tocar prod Sentinel systemd/DB desde este proyecto.

---

## Como probar rapido

1. `/status` — umbral 85 y sequential.
2. `/reporte` — misma info + politica.
3. `/task` corto — vía ligera (rápida).
4. `/concilio` solo si quieres heavy (tarda; usa RAM).
5. Abrir `/mini` en el puerto **8002**.
6. (Opcional) HTTPS y boton Mini App en `/start`.


---

## Services (host)

| Unit | Rol | Notas |
|------|-----|-------|
| `consensus-telegram.service` | `telegram_bot.py` | `enabled`/`active` (usuario `deamon`) |
| `consensus-web.service` | Mini App / web UI `:8002` | `enabled`/`active` |
| `ollama.service` (Kali) | — | **disabled** a proposito: API `:11434` la sirve Windows `ollama.exe` |

Auth: todos los comandos/callbacks pasan por `is_authorized` (`TELEGRAM_CHAT_ID`).

