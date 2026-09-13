# Local

Monorepo índice de sistemas locales en WSL Kali (**deamon** / X-Deamon).

`main` solo contiene este índice + LICENSE. El código de cada sistema vive en su propia rama huérfana (raíz limpia por sistema).

## Ramas de sistema

| Rama | Sistema | Origen local | Archivos |
|------|---------|--------------|----------|
| `local/home-bridge` | Home bridge / DeamonX móvil | `/home/deamon` (README, AGENTS, CHANGELOG, `bridge/`, docs DeamonX) | 13 |
| `local/concilio` | Consensus / Concilio expert agent | `/home/deamon/consensus-expert-agent` | 59 |
| `local/padron` | Padrón de afiliados (Streamlit) | `/home/deamon/padron_afiliados_app` | 10 |
| `local/sentinel-omega` | Sentinel Ω (workspaces) | `/home/deamon/workspaces` | 1639 |
| `local/watchdog` | Watchdog — monitor de seguridad por cron | `/watchdog` (Kali) | 42 |

Conteos medidos el 2026-09-13 sobre `home-bridge@b80548b`, `concilio@c11df3f`,
`padron@49caaac`, `sentinel-omega@8ed0681` y `watchdog@358f2ee`. Cambian con cada
push: `git ls-tree -r --name-only origin/<rama> | wc -l` da el valor vigente.

### Ramas de snapshot

Nacieron como cortes congelados de otra rama, con nombre de versión. **Ya no lo
están:** ambas recibieron commits después de creadas, así que hoy no representan
ni un tag ni el estado vigente de su sistema.

| Rama | Nació como | Estado al 2026-09-13 |
|------|------------|----------------------|
| `local/concilio-2.2.6-20260913` | corte de `local/concilio` en `f4abb65` | Ahí sigue, pero `local/concilio` avanzó a `c11df3f`. Difieren en `README.md`, `CHANGELOG.md` y `LICENSE`: el snapshot es anterior a todos |
| `local/deamonx-bridge-v1.0.0` | subconjunto de `local/home-bridge` (`bridge/` + `docs/`) | Avanzó a `562634e`: le añadieron `docs/AUDIT_GITHUB_20260913.md` y un `CHANGELOG.md`. Ya no es un subconjunto estricto |

Si la intención era tener tags, conviene crearlos (ver deuda #7) y dejar de
empujar a estas ramas — cada commit nuevo las aleja de ser el corte que su
nombre promete.

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

- Secretos: no hay `.env`, `*.pem`, `*.key` ni `id_rsa` en ninguna rama. Solo
  `.env.example`: uno en `concilio`, uno en `watchdog`, y **dos** en
  `sentinel-omega` (`workspaces/deploy/.env.example` y
  `workspaces/sentinel_omega/.env.example`).
- Bases de datos binarias (`*.db`, `*.sqlite`) y entornos virtuales (`venv/`, `.venv/`).
  Solo se versiona el DDL (`schema.sql`, `schema_parts/`).

`local/sentinel-omega` **sí** incluye los modelos `.onnx` entrenados porque el
pipeline los carga directo desde el árbol. Tras el archivado de la deuda #2, en
`a0bb343` hay 13: **7 vigentes** en `sentinel_omega/models/` (los que el sistema
usa, `beta2_atmospheric_cnn.onnx` el mayor con ~780 KB) y 6 conservados en
`_archive/20260913/models_nested/`.

## Deuda conocida

Estado al 2026-09-13. La columna **Estado** dice en qué punto está cada uno. Se
conservan los cerrados para que quede el rastro de qué se hizo, dónde y con qué
criterio. De los 9, **queda 1 abierto** (#9), uno bloqueado por permisos (#7) y
uno informativo (#8). Los demás están cerrados: cuatro por trabajo hecho (#2,
#3, #4, #1) y dos por decisión documentada del autor (#5, #6) — una decisión
explícita cierra una deuda igual que un commit, siempre que quede escrita.

| # | Rama | Asunto | Estado |
|---|------|--------|--------|
| 1 | `local/sentinel-omega` | Los 4 workflows (`bandit`, `codeql`, `copy-delta-to-snt`, `roy-vigilante`) nunca se ejecutaron: vivían en `workspaces/.github/workflows/` y GitHub solo lee `.github/workflows/` en la raíz del repo; los `schedule:` además solo disparan desde la rama por defecto | **Cerrado en `8ed0681`** (decisión del autor): eliminados de la rama. La operación queda 100% en systemd local (`deploy/*.service` y `.timer`). Siguen recuperables con `git show 8ed0681^:workspaces/.github/workflows/<archivo>` |
| 2 | `local/sentinel-omega` | Árbol de modelos duplicado | **Resuelto en `b639aa8`** (Agente-C): los 6 ONNX anidados + su `models_meta.json` se movieron a `_archive/20260913/models_nested/` (renames `R100`, byte a byte idénticos) y `loki_unificado_rf.onnx` se borró por ser el mismo blob `e27bb4b` que el canónico. Quedan 7 ONNX en `sentinel_omega/models/`. Diagnóstico previo: el canónico es `sentinel_omega/models/` (meta del 2026-09-13T09:05Z, alfa1 n=1388 / beta1 n=2082 / omega n=2726). El anidado `sentinel_omega/sentinel_omega/models/` es copia congelada del 2026-09-11T00:20Z (n=1303 / 1997 / 2556). El `path` absoluto de **ambos** meta apunta al de primer nivel, igual que el `base_dir` por defecto de `config/onnx_config.py`. Falta decidir si se borra la copia |
| 3 | `local/sentinel-omega` | Respaldos manuales versionados | **Resuelto.** `b639aa8` sacó 40 archivos y archivó el tarball `_SCHEMA_PARTS_BACKUP_PRE_FIX.tar.gz`; `e70e462` archivó los 2 que el glob `*.bak*` no alcanzó por su nombre (`launcher.py.broken-2026-09-10`, `launcher_fixed.py`) en `_archive/20260913/launchers/` |
| 4 | `local/padron`, `local/sentinel-omega` | Symlinks de skills apuntando dentro de `venv/`/`.venv/` (gitignorado): rotos en cualquier clon | **Resuelto.** El de `sentinel-omega` en `b639aa8`; los dos de `local/padron` en `49caaac`, fuera del índice y añadidos al `.gitignore` con el motivo escrito. El symlink `sentinel_omega/sentinel_omega/data → ../data` se conserva a propósito: resuelve bien |
| 5 | `local/sentinel-omega` | `estado/` crece por ejecución (1117 de 1639 archivos, 68% de la rama) | **Cerrado por decisión del autor (`8ed0681`):** sin retención ni purga, igualando a `Inzainos/workspaces` (main), que tampoco poda. Se asume el crecimiento a cambio de conservar el histórico completo |
| 6 | `local/sentinel-omega` | `LICENSE` de raíz (y `workspaces/LICENSE`) dicen MIT mientras `workspaces/sentinel_omega/pyproject.toml` dice `Proprietary — Fractal Core Research` | **Cerrado por decisión del autor (`8ed0681`):** sin cambio. `Inzainos/workspaces` (main) declara la misma combinación, así que es el patrón establecido entre monorepo y subproyecto, no una contradicción accidental |
| 7 | — | El remoto no tiene tags. Las dos ramas de snapshot deberían serlo | **Bloqueado:** el push de `refs/tags/*` se deniega con HTTP 403 desde esta sesión (los pushes a `refs/heads/*` sí pasan). Hay que crearlos desde la katana |
| 8 | `local/sentinel-omega` | `_archive/20260913/` es material conservado a propósito (ONNX anidados, tarball de schema, variantes del launcher), no basura. Su `README.md` explica qué hay dentro y cómo revertir | Informativo |
| 9 | `local/sentinel-omega` | Dos cosas importables se llaman `sentinel_omega`: el directorio de proyecto (tiene `__init__.py`) y el paquete anidado que declara el `egg-info`. Es la causa de que los modelos se duplicaran | **Pendiente: requiere correr la suite.** Ver nota abajo |

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

### Nota sobre la deuda #9 — por qué no se tocó

El diagnóstico inicial fue "quitar el `__init__.py` del directorio de proyecto".
Es más sutil que eso: desde Python 3.3, un directorio **sin** `__init__.py` sigue
siendo importable como *namespace package* (PEP 420). Quitarlo no elimina el
nombre; lo degrada a porción de namespace, que pierde precedencia frente a un
paquete regular encontrado después en `sys.path`. Si el paquete está instalado
como editable (`pip install -e .`, que es lo que sugiere el `egg-info`), el
destino apunta de vuelta al mismo árbol y el arreglo puede no cambiar nada.

Verificarlo exige correr los ~420 tests con las dependencias reales instaladas
(`numpy`, `scipy`, `pandas`, `onnxruntime`), que no están disponibles en el
entorno donde se hizo esta auditoría. Por eso queda pendiente en vez de
empujarse a ciegas: es un cambio de una línea con capacidad de romper imports
en todo el sistema.
