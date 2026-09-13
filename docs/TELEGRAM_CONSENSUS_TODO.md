# Telegram + Consensus — trabajo pendiente (cuando X-Deamon esté online)

## Leer primero (no romper)
- `/home/deamon/consensus-expert-agent/{README,AGENTS,CONCILIO,CHANGELOG,TELEGRAM_BOT_README}.md`
- `/home/deamon/AGENTS.md`
- Sentinel Dev: `infrastructure/messaging/consenso_vigilante.py`, `alert_service.py`, `api/telegram.py`, `static/mini.html`

## Política de alertas (Sentinel)
- Digest **cada hora** siempre (aunque esté calmado).
- Telegram **inmediato** solo eventos **sin precedentes** (firma nueva, patrón cimática nuevo, muro novel, SYSTEM_DEAD).

## Añadir / arreglar
1. Reportes de estado en el bot Consensus (`/status` enriquecido: Ollama models unloaded?, umbral 85, última sesión `.concilio`, cola `alert_queue.get_stats()`).
2. Comando o botón **Reporte** que resuma: Concilio health + (si bridge) Sentinel overview sin secretos.
3. Miniapp Telegram: página HTTPS estática (o servida por FastAPI `/mini`) con estado + link a dashboard; `TELEGRAM_WEBAPP_URL` en `.env`.
4. Actualizar `TELEGRAM_BOT_README.md` + CHANGELOG.
5. Tests dry-run / py_compile; no commitear `.env`.

## No hacer
- No reescribir orchestrator Concilio a ciegas si otro agente está en el repo.
- No pegar tokens en código.
- No tocar prod systemd.

## DONE 2.2.2 (2026-09-10)
- /status + /reporte enriquecidos
- static/mini.html + /mini + /api/mini/status (+ /api/concilio/health, /api/alerts/stats)
- WebApp button gated on HTTPS TELEGRAM_WEBAPP_URL
- Docs + CHANGELOG actualizados
- Leftover: HTTPS publico para WebApp
