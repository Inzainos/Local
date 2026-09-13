# AGENTS.md — Watchdog

Guía operativa para agentes de IA que trabajen en esta rama (Claude Code, Cursor,
Copilot, Codex, etc.). Es el archivo neutral que leen todas las herramientas.
La descripción completa del sistema está en [`watchdog/README.md`](watchdog/README.md).

## Qué es este repo

Monitor de seguridad continuo para la máquina Kali (WSL2) del entorno X-Deamon,
corriendo por cron. Alcance: **detección y contención en este host**. No es un
framework ofensivo, no es un agente autónomo, y no aprende TTPs de atacantes.

## Comandos

```bash
# Un ciclo manual
cd /watchdog && PYTHONPATH=/watchdog/src .venv/bin/python -m watchdog.main --mode light
cd /watchdog && PYTHONPATH=/watchdog/src .venv/bin/python -m watchdog.main --mode heavy

# Tests
cd /watchdog && .venv/bin/pytest tests/ -v

# Entrenar el detector de anomalías (necesita ~200 muestras reales en metrics_history)
cd /watchdog && .venv/bin/python scripts/train_baseline.py

# Instalar/reinstalar los cron jobs
bash scripts/install_cron.sh
```

## Reglas duras (no romper)

1. **Secretos solo por entorno.** Las API keys (`VT_API_KEY`, `OTX_API_KEY`,
   `ABUSEIPDB_API_KEY`, `OPENROUTER_API_KEY`, `TELEGRAM_*`) se leen de `.env`,
   que está en `.gitignore`. Nunca hardcodear ni imprimir una key en un log.
   Todas son opcionales: sin ellas el pipeline degrada a heurística local, no falla.
2. **Nunca acción automática sobre certificados.** Un cambio en el cert store se
   reporta siempre como `alert_only`. Borrar un CA real a ciegas rompe TLS en toda
   la máquina.
3. **Nunca revertir persistencia automáticamente.** Cambios en `authorized_keys`,
   `sudoers.d` o crontab son `alert_only`. "Arreglar" sudoers mal deja al usuario
   sin acceso al sistema.
4. **Forense antes de tocar.** Cualquier acción sobre un hallazgo guarda primero
   el JSON forense (cadena de procesos padre, archivos abiertos, conexiones) en
   `data/forensics/` y registra el incidente en la tabla `incidents`.
5. **Borrado automático solo con confianza muy alta:** VirusTotal
   `positives >= 15` **y** `total >= 70` **y** OTX confirmando el mismo hash con
   al menos un pulse. El umbral vive en `config/config.yaml -> policy`; no
   relajarlo sin justificación escrita en el CHANGELOG.
6. **Siempre generar logs.** Toda corrida escribe a `logs/watchdog.log`. Un cambio
   que agregue un paso al pipeline agrega su línea de log correspondiente.
7. **`data/` y `logs/` no se versionan.** Solo los `.gitkeep`. La DB, la cuarentena,
   el forense y el modelo ONNX entrenado son locales de cada máquina.
8. **Falsos positivos: excluir, no silenciar.** Si un venv o un directorio nuevo
   genera ruido en `integrity_scan`/`chkrootkit`, se agrega la ruta a
   `config.yaml -> exclude_paths`. No se desactiva el scanner.
9. **Los tests deben pasar** antes de commitear cambios de código.

## Política de respuesta (resumen)

| Hallazgo | Acción |
|---|---|
| Señal real (intel positiva o heurística de proceso/archivo) | Cuarentena: mover a `data/quarantine/`, `chmod 000`, matar el proceso |
| VT `positives>=15` + `total>=70` + OTX con pulse | Borrado automático |
| Cambio en cert store | `alert_only` — revisión humana |
| Cambio en `authorized_keys` / `sudoers.d` / crontab / código de watchdog | `alert_only` — revisión humana |

Restaurar un falso positivo: `watchdog.response.quarantine.restore(logger, ruta_cuarentena, ruta_original)`.

## Limitaciones conocidas (no las borres del README)

- Si un atacante ya tiene root puede editar `watchdog.db`, donde vive el baseline
  de persistencia. Es detección temprana, no garantía criptográfica — por eso
  existe el backup off-box diario hacia el lado Windows (`scripts/offbox_backup.sh`,
  que a propósito **no** copia `data/quarantine/`).
- `rkhunter` y `chkrootkit` necesitan `sudo NOPASSWD` acotado a esos dos binarios.
  Sin eso, `os_scan.py` loguea que no pudo correrlos y sigue: se pierde cobertura,
  no se rompe el ciclo.

## Git

- Esta es una **rama huérfana** del monorepo `Inzainos/Local`: raíz limpia, sin
  historia compartida con `main` ni con las otras ramas `local/*`.
- `main` solo contiene el índice del monorepo. No mezclar código aquí con `main`.
- No pushear a otra rama sin permiso explícito.
- Los PRs se abren como **draft**.
