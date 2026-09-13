# Watchdog — monitor de seguridad continuo

Rama del monorepo [`Inzainos/Local`](https://github.com/Inzainos/Local). Ver también
`local/home-bridge`, `local/concilio`, `local/padron` y `local/sentinel-omega`.

Origen local: `/watchdog` en WSL2 Kali (**deamon** / X-Deamon).

## Qué es

Monitor de seguridad por cron para esta máquina: escaneo liviano cada 15 minutos y
escaneo pesado cada hora, este último cerrando con auditoría de integridad
(procesos vs paquetes instalados, certificados de confianza) y de persistencia
(`authorized_keys`, `sudoers.d`, crontab, y el propio código de watchdog).

Los hallazgos se enriquecen con VirusTotal, AlienVault OTX y AbuseIPDB, se
guardan en SQLite con memoria de IOCs, y se resuelven según una política de
cuarentena/borrado configurable. Incluye detección de anomalías de comportamiento
con un IsolationForest entrenado sobre la línea base de *esta* máquina y
exportado a ONNX, más triage opcional asistido por LLM vía OpenRouter.

**Documentación completa del sistema:** [`watchdog/README.md`](watchdog/README.md)
— arquitectura, setup, permisos sudo necesarios, API keys, política de respuesta,
falsos positivos conocidos y backup off-box.

**Reglas para agentes de IA:** [`AGENTS.md`](AGENTS.md).

## Estructura

```
watchdog/
├── config/config.yaml        intervalos, exclusiones, umbrales de política
├── src/watchdog/
│   ├── main.py               orquestador (--mode light|heavy)
│   ├── scanners/             network, host, os, integrity, persistence
│   ├── intel/                VirusTotal, AlienVault OTX, AbuseIPDB
│   ├── anomaly/              IsolationForest → ONNX (baseline entrena, detector evalúa)
│   ├── response/             policy (alert_only|quarantine|auto_delete) + quarantine
│   ├── llm/triage.py         explicación opcional vía LLM
│   └── storage/db.py         SQLite: incidents, ioc_memory, metrics_history,
│                             cert_baseline, persistence_baseline
├── scripts/                  install_cron.sh, train_baseline.py, offbox_backup.sh
├── data/                     quarantine/, forensics/, baseline/, watchdog.db (gitignored)
└── logs/                     watchdog.log, cron.log (gitignored)
```

## Instalación

```bash
cd /watchdog
cp .env.example .env          # todas las API keys son opcionales
bash scripts/install_cron.sh  # crea venv, instala deps y registra los cron jobs
```

Sin ninguna key configurada sigue funcionando en modo heurístico puro; solo pierde
el enriquecimiento externo. Detalle de permisos `sudo NOPASSWD` para
`rkhunter`/`chkrootkit` en [`watchdog/README.md`](watchdog/README.md).

## Qué NO es

El propio `watchdog/README.md` lo declara de entrada: no es un agente autónomo que
aprenda tácticas de atacantes reales, y no borra nada a ciegas. El IsolationForest
aprende cómo se ve *esta* máquina en condiciones normales, no el modus operandi de
un adversario.
