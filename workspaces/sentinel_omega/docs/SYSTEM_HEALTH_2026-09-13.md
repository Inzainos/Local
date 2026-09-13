# System Health — 2026-09-13

Actualizado post fix dual-launcher / Telegram + política Ollama + backup catch-up. Detalle: SESSION_2026-09-13.md.

## Overall: GREEN (con amber operativo en scheduler)

| Área | Estado | Nota |
|------|--------|------|
| sentinel-omega | GREEN — active | Un solo launcher |
| sentinel-omega-scheduler | AMBER — disabled | Intencional; evita ciclo #1 dual |
| Launchers | GREEN — 1 | No dual launcher.py |
| Telegram / consensus-web | GREEN — active | Alertas + web |
| Dashboard API :8788 / UI :5174 | GREEN | Apunta a Prod DB |
| Ollama :11434 | GREEN — API 200 | Via Windows ollama.exe; Kali service disabled |
| Offbox backup | GREEN | Catch-up watchdog_2026-09-13_1253.tar.gz (gap Sep 12 por WSL asleep) |
| Pytest Alfa2 / Schumann | GREEN | 7 passed; Schumann espera None (sin fake 7.83) |

## Pendientes
- Firmas --entrenar opcional
- Prod enable gate
- Mantener scheduler disabled y watchdog sin auto-restart del scheduler
