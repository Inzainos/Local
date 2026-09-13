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

Cada una de las **cinco ramas de sistema** de arriba incluye en su raíz `README.md`,
`AGENTS.md`, `CHANGELOG.md` y `LICENSE` (sin secretos), más la cabecera que enlaza de
vuelta a este índice.

Las dos ramas de snapshot no: son cortes congelados y quedaron fuera de esa
normalización. `local/deamonx-bridge-v1.0.0` solo trae `bridge/` + `docs/`, sin ningún
archivo de raíz; `local/concilio-2.2.6-20260913` conserva `README.md`, `AGENTS.md` y
`CHANGELOG.md` pero es anterior al `LICENSE`, así que tampoco lo tiene.

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

Estado al 2026-09-13. Las ramas reflejan el árbol de la máquina Kali y su contenido
no se modifica desde aquí; lo que sigue está documentado en cada rama, no resuelto.

| # | Rama | Asunto | Estado |
|---|------|--------|--------|
| 1 | `local/sentinel-omega` | Workflows en `workspaces/.github/workflows/` — GitHub solo lee `.github/workflows/` en la raíz, así que hoy no corre ningún CI (`bandit`, `codeql`, `copy-delta-to-snt`, `roy-vigilante`). Los `schedule:` además solo disparan desde la rama por defecto | Documentado |
| 2 | `local/sentinel-omega` | Árbol de modelos duplicado | **Resuelto el diagnóstico:** el canónico es `sentinel_omega/models/` (meta del 2026-09-13T09:05Z, alfa1 n=1388 / beta1 n=2082 / omega n=2726). El anidado `sentinel_omega/sentinel_omega/models/` es copia congelada del 2026-09-11T00:20Z (n=1303 / 1997 / 2556). El `path` absoluto de **ambos** meta apunta al de primer nivel, igual que el `base_dir` por defecto de `config/onnx_config.py`. Falta decidir si se borra la copia |
| 3 | `local/sentinel-omega` | Respaldos manuales versionados: `launcher_hex_backup_1788196565/`, `launcher.py.broken-2026-09-10`, `launcher_fixed.py`, `*.bak_ingest_20260910_183137`, `*.bak_delta_20260910` | Documentado |
| 4 | `local/padron`, `local/sentinel-omega` | Symlinks `.claude/skills/` y `.agents/skills/developing-with-streamlit` apuntan dentro de `venv/`/`.venv/` (gitignorado): quedan rotos en cualquier clon hasta crear el entorno con Streamlit | Documentado |
| 5 | `local/sentinel-omega` | `estado/` crece por ejecución (1117 de 1677 archivos, 67% de la rama). Evaluar retención o Git LFS | Documentado |
| 6 | `local/sentinel-omega` | `LICENSE` de raíz dice MIT y `workspaces/sentinel_omega/pyproject.toml` dice `Proprietary — Fractal Core Research` | Documentado |
| 7 | — | El remoto no tiene tags. Las dos ramas de snapshot deberían serlo | **Bloqueado:** el push de `refs/tags/*` se deniega con HTTP 403 desde esta sesión (los pushes a `refs/heads/*` sí pasan). Hay que crearlos desde la katana |

### Tags pendientes

Los mensajes ya están redactados; falta ejecutarlos desde una máquina con permiso
de escritura sobre `refs/tags/*`:

```bash
git tag -a concilio-2.2.6 f4abb65 -m "Concilio 2.2.6 (2026-09-13)"
git tag -a deamonx-bridge-v1.0.0 6ef194b -m "DeamonX bridge v1.0.0 (2026-09-13)"
git push origin concilio-2.2.6 deamonx-bridge-v1.0.0
```

Las ramas `local/concilio-2.2.6-20260913` y `local/deamonx-bridge-v1.0.0` se
conservan tal cual: los tags no las reemplazan hasta que se decida borrarlas.
