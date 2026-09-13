# Local

Monorepo índice de sistemas locales en WSL Kali (**deamon** / X-Deamon).

`main` solo contiene este índice + LICENSE. El código de cada sistema vive en su propia rama huérfana (raíz limpia por sistema).

## Ramas de sistema

| Rama | Sistema | Origen local | Archivos |
|------|---------|--------------|----------|
| `local/home-bridge` | Home bridge / DeamonX móvil | `/home/deamon` (README, AGENTS, CHANGELOG, `bridge/`, docs DeamonX) | 11 |
| `local/concilio` | Consensus / Concilio expert agent | `/home/deamon/consensus-expert-agent` | 58 |
| `local/padron` | Padrón de afiliados (Streamlit) | `/home/deamon/padron_afiliados_app` | 11 |
| `local/sentinel-omega` | Sentinel Ω (workspaces) | `/home/deamon/workspaces` | 1677 |
| `local/watchdog` | Watchdog — monitor de seguridad por cron | `/watchdog` (Kali) | 40 |

### Ramas de snapshot (equivalen a un tag, no reciben trabajo nuevo)

| Rama | Equivale a | Nota |
|------|------------|------|
| `local/concilio-2.2.6-20260913` | `local/concilio` | Mismo commit exacto (`f4abb65`); sin diferencias |
| `local/deamonx-bridge-v1.0.0` | subconjunto de `local/home-bridge` | Solo `bridge/` + `docs/`; `home-bridge` añade README/AGENTS/CHANGELOG |

## Uso rápido

```bash
git clone -b local/home-bridge    https://github.com/Inzainos/Local.git Local-home-bridge
git clone -b local/concilio       https://github.com/Inzainos/Local.git Local-concilio
git clone -b local/padron         https://github.com/Inzainos/Local.git Local-padron
git clone -b local/sentinel-omega https://github.com/Inzainos/Local.git Local-sentinel-omega
git clone -b local/watchdog       https://github.com/Inzainos/Local.git Local-watchdog
```

Cada rama incluye su propio `README.md` y `AGENTS.md` (sin secretos).

## Qué contiene cada sistema

- **`local/home-bridge`** — Mapa maestro del home `deamon` y puente SSH hacia el nodo móvil
  DeamonX (Termux / Honor X7d): `bridge/install_sshd.sh`, `bridge/check_bridge.sh`,
  configs `sshd_*`, y docs `DEAMONX_MOBILE.md` / `DEAMONX_BRIDGE_2026-09-13.md`.
  Túnel SSH `-L 11434` con Ollama en loopback, pubkey-only.
- **`local/concilio`** — Pipeline secuencial sobre Ollama: `lightest → medium → heavy →
  lightest verify`, umbral 85/100, máx. 3 rondas, un modelo cargado a la vez.
  `agents/`, `engine/`, `memory/` (incluye `anti_injection.py`), `modelfiles/`,
  units systemd en `deploy/`, bridge Telegram (`/task`, `/concilio`) y Mini App `:8002`.
- **`local/padron`** — Dashboard Streamlit de 11 pestañas (`src/app_afiliados.py`) +
  análisis estadístico y cimático FFT/autocorrelación (`src/analisis_comportamiento.py`),
  esquema SQLite en `database/schema.sql`, tests en `tests/`.
- **`local/sentinel-omega`** — Detección de precursores de eventos naturales: 6 agentes +
  Padre + Juez (ciclo 2 h), schema v11 con LOCF, launcher auto-expandible desde
  `launcher_hex/`, `AlertService` unificado y `ReportEngine` versionado, dashboard por
  pestañas. Incluye `estado/` con 1117 reportes MX/ejecutivos ya generados.
- **`local/watchdog`** — Monitor de seguridad por cron (liviano 15 min / pesado 1 h +
  auditoría de integridad). Scanners host/red/OS/integridad/persistencia, enriquecimiento
  VirusTotal + AlienVault OTX + AbuseIPDB, IOCs en SQLite, anomalías con IsolationForest
  exportado a ONNX, política de cuarentena configurable y triage opcional vía LLM.

## Qué NO se sube

- Secretos: no hay `.env`, `*.pem`, `*.key` ni `id_rsa` en ninguna rama. Solo `.env.example`
  (en `concilio`, `watchdog` y `sentinel-omega/workspaces/deploy`).
- Bases de datos binarias (`*.db`, `*.sqlite`) y entornos virtuales (`venv/`, `.venv/`).
  Solo se versiona el DDL (`schema.sql`, `schema_parts/`).

`local/sentinel-omega` **sí** incluye los modelos `.onnx` entrenados (14 archivos,
~780 KB el mayor) porque el pipeline los carga directo desde el árbol.

## Deuda conocida

Pendientes detectados el 2026-09-13, aún sin resolver en sus ramas:

| # | Rama | Asunto |
|---|------|--------|
| 1 | `local/sentinel-omega` | Workflows en `workspaces/.github/workflows/` — GitHub solo lee `.github/workflows/` en la raíz, así que hoy no corre ningún CI (`bandit`, `codeql`, `copy-delta-to-snt`, `roy-vigilante`). Los `schedule:` además solo disparan desde la rama por defecto |
| 2 | `local/sentinel-omega` | Árbol de modelos duplicado: `sentinel_omega/models/` y `sentinel_omega/sentinel_omega/models/` con los mismos nombres y contenidos distintos (salvo `loki_unificado_rf.onnx`, blob idéntico). Falta definir cuál es el canónico |
| 3 | `local/sentinel-omega` | Respaldos manuales versionados: `launcher_hex_backup_1788196565/`, `launcher.py.broken-2026-09-10`, `launcher_fixed.py`, `*.bak_ingest_20260910_183137`, `*.bak_delta_20260910` |
| 4 | `local/padron`, `local/sentinel-omega` | Symlinks `.claude/skills/` y `.agents/skills/developing-with-streamlit` apuntan dentro de `venv/`/`.venv/` (gitignorado): quedan rotos en cualquier clon hasta crear el entorno con Streamlit |
| 5 | `local/sentinel-omega` | `estado/` crece por ejecución (1117 de 1677 archivos, 67% de la rama). Evaluar retención o Git LFS |
| 6 | — | Las dos ramas de snapshot deberían ser tags anotados; hoy el remoto no tiene ningún tag |
