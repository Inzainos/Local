# Changelog — Watchdog

Cambios relevantes de esta rama. Convenciones de
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Fechas en hora local MX (UTC-6).

---

## [Unreleased] — 2026-09-13 — Metadata de rama

### Added
- `README.md` de raíz: descripción del sistema, estructura, instalación y alcance.
  Antes era el stub de dos líneas heredado del `main` del monorepo.
- `AGENTS.md`: reglas duras para agentes de IA — secretos solo por entorno, nunca
  acción automática sobre certificados ni sobre persistencia, forense antes de
  tocar, umbrales de borrado automático, logs obligatorios, y las limitaciones
  conocidas que no deben borrarse del README.
- `CHANGELOG.md` (este archivo).

### Notes
- Sin cambios en el código de `watchdog/`: la rama refleja el árbol `/watchdog`
  de la máquina Kali tal como está.

---

## [Initial] — 2026-09-13 — Sync del árbol `/watchdog` de Kali

### Added
- Pipeline por cron: `--mode light` cada 15 min, `--mode heavy` cada hora.
- Scanners: `network_scan` (ss liviano + nmap pesado con diff vs corrida previa),
  `host_scan` (procesos sospechosos + captura forense + métricas),
  `os_scan` (wrappers rkhunter/chkrootkit/clamscan),
  `integrity_scan` (procesos vs dpkg, certificados vs baseline),
  `persistence_scan` (authorized_keys, sudoers.d, crontab, self-integrity).
- Threat intel: VirusTotal, AlienVault OTX, AbuseIPDB — todas opcionales.
- Anomalías: IsolationForest entrenado sobre la línea base del host, exportado a ONNX.
- Respuesta: `policy.py` (alert_only | quarantine | auto_delete) + `quarantine.py`
  (mover, `chmod 000`, matar proceso, borrar si corresponde, restaurar).
- Persistencia: SQLite con `incidents`, `ioc_memory`, `metrics_history`,
  `cert_baseline`, `persistence_baseline`.
- Triage opcional por LLM vía OpenRouter (`llm/triage.py`).
- Scripts: `install_cron.sh`, `train_baseline.py`, `offbox_backup.sh`
  (backup diario 03:30 hacia el lado Windows, retención 30 días, sin cuarentena).
- `config/config.yaml` con intervalos, CIDR de la LAN, rutas de datos, umbrales de
  política y `exclude_paths` derivados de la auditoría manual previa (venvs,
  node_modules y site-packages generaban falsos positivos en chkrootkit).
