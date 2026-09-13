# Home Workspace — /home/deamon/

Repositorio base para **todos los proyectos** en el home de `deamon` (WSL2 Kali Linux).  
Contiene tres proyectos principales (+ nodo móvil DeamonX en el ecosistema Concilio/Sentinel):

| Proyecto | Ubicación | Descripción |
|----------|-----------|-------------|
| **Sentinel Omega** | `/home/deamon/workspaces/sentinel_omega/` (preferir `workspaces-dev` → `workspaces-test` → `workspaces`) | Detección de precursores de eventos naturales (sismos, volcanes, tormentas solares). 6 agentes + Padre + Juez. Dashboard 11 tabs. Alertas Telegram con gráficas/tablas/cimática. |
| **Padrón de Afiliados** | `/home/deamon/padron_afiliados_app/` | Sistema de control electoral — Dashboard Streamlit 11 pestañas + alertas Telegram. Análisis demográfico, participación, cohortes, cimática (FFT/autocorr), redes, outliers. |
| **Concilio** (`consensus-expert-agent`) | `/home/deamon/consensus-expert-agent/` | Pipeline secuencial Ollama (umbral **85%**). Telegram: `/task` ligero / `/concilio` heavy / Mini App `:8002` + HTTPS `cloudflared-mini`. Ollama API = Windows `:11434` (Kali unit disabled). |
| **DeamonX Mobile** | /home/deamon/docs/DEAMONX_MOBILE.md + ~/bridge/TERMUX.md | Nodo Termux (Honor X7d): gateway :8090, Ollama remoto vía túnel SSH 127.0.0.1:11434, modelo concilio-lightest:latest. GO 2026-09-13. |

---

## DeamonX Mobile (2026-09-13)

Nodo móvil Honor X7d / Termux. Arquitectura, REMOTE vía túnel SSH, modelo concilio-lightest:latest y checklist GO:

- Doc nodo: [docs/DEAMONX_MOBILE.md](docs/DEAMONX_MOBILE.md)
- Resumen puente (2026-09-13): [docs/DEAMONX_BRIDGE_2026-09-13.md](docs/DEAMONX_BRIDGE_2026-09-13.md)
- Ops túnel: [bridge/TERMUX.md](bridge/TERMUX.md)

---

## Estado Actual (2026-09-13)

**Ops del día (corto):**
- Puente **DeamonX-Mobile** ↔ X-Deamon: SSH pubkey-only, túnel `-L 11434`, Ollama solo en loopback (`REMOTE_OLLAMA_URL=http://127.0.0.1:11434`, `REMOTE_MODEL=concilio-lightest:latest`). Docs: [`bridge/TERMUX.md`](bridge/TERMUX.md), [`docs/DEAMONX_BRIDGE_2026-09-13.md`](docs/DEAMONX_BRIDGE_2026-09-13.md).
- Host: Wi-Fi Private + firewall WSL SSH 22; autostart Kali (`WSL-Kali-Autostart`); Ollama = Windows `ollama.exe` (Kali `ollama.service` disabled); `jq` + scripts en `~/bridge/`.
- Sentinel: scheduler disabled, 1 launcher; docs SESSION/SYSTEM_HEALTH 2026-09-13 ya existen.
- Concilio: `/task` light + pack, `/concilio` heavy, Mini App `cloudflared`. Roles: G coord/sudo · C host/sshd · T Concilio/TG · A DeamonX mobile.

### Snapshot previo (detalle por proyecto; base 2026-09-03 + ops posteriores)


### Sentinel Omega — v2.5.3 (Producción)
- **Tests**: 430/430 ✅
- **Consenso**: Arquitectura "Padre" — validación jerárquica Junior→Senior, pesos disciplinarios (Juez), cross-family check, Schumann correlation anchor, Omega dual-ask, pérdida asimétrica (miss_penalty=10×).
- **Watchdog**: `NetworkWatchdog` (systemd, 60s interval, 3 fails threshold, DNS+HTTP checks, auto-restart services).
- **Telegram**: `AlertService` unificado + `charts.py` (fantasma_timeline, cimatica_bars, precursores_tabla_png) + templates enriquecidos.
- **Dashboard**: 11 tabs (Alfas, Betas, Omega, Padre, Juez, Eventos, Agente/Consenso, Cimática, Fantasma, Reportes, Config).
- **Git**: Rama `local/alertas-v2.5.3` (conforme a convención `local/<feature>-v<version>`).

### Padrón de Afiliados — v1.0.0 (Esqueleto)
- **Tests**: 2/2 ✅ (integración + resumen ejecutivo)
- **DB**: SQLite con 6 tablas (`afiliados`, `eventos_electorales`, `participacion_electoral`, `historial_cambios`, `alertas`, `sqlite_sequence`) + vista `v_estadisticas_generales`.
- **Módulo análisis**: `analisis_comportamiento.py` — demográfico, participación, cohortes, cimática (FFT/autocorr), redes, outliers, reportes JSON.
- **Streamlit**: 11 tabs (Dashboard, Afiliados, Importar, Análisis, Eventos, Participación, Alertas, Telegram, Cimática, Redes, Config).
- **Git**: Repo independiente en `/home/deamon/padron_afiliados_app/` — **sin commits aún**, pendiente rama `local/padron-v1.0.0`.


### Concilio — consensus-expert-agent v2.2.1 (Standalone thin)
- **Pipeline**: LIGHTEST → MEDIUM → HEAVY → LIGHTEST verify; reentrada si score &lt; 85; máx. 3 rondas; un modelo Ollama a la vez.
- **Modelos**: `concilio-worker` / `concilio-arbitro` (aliases lightest|medium|heavy); bases `qwen2.5:1.5b` + `gemma4:26b` (ya no identidad Nemotron/DeepSeek).
- **Policy**: `inject_sentinel_architecture: false` hasta que terminen updates Sentinel en otro hilo; `.concilio` = DATA; fast Gente/Estado fuera del Concilio.
- **Telegram**: bot bidireccional Consensus ↔ alertas Sentinel (tokens solo por env).
- **Docs**: `README.md`, `CONCILIO.md`, `AGENTS.md` local + stub `data/memory_packs/home_hard_rules_stub.md`.
- **Git**: repo independiente en `/home/deamon/consensus-expert-agent/`.


---

## Reglas Operativas (AGENTS.md)

Este workspace usa `AGENTS.md` como guía central para agentes y colaboradores. Puntos clave:

- **Secretos solo por variables de entorno** (nunca hardcodeados).
- **Cero datos sintéticos**: faltantes como `NULL` y datos derivados etiquetados.
- **`data/` no se versiona** y puede no existir en entornos limpios.
- **Reportes versionados** en `estado/historial/` (no sobrescribir historial).
- **Migraciones de esquema solo forward-only**.
- **Antes de commitear, tests deben pasar**.
- **Git convention**: ramas `local/<feature>-v<version>` (ej. `local/alertas-v2.5.3`), **nunca push directo a `main`**.

Ver `AGENTS.md` para detalle completo.

---

## Comandos Principales

```bash
# ===== SENTINEL OMEGA =====
cd /home/deamon/workspaces/sentinel_omega

# Tests (SIEMPRE desde la raíz del workspace, PYTHONPATH requerido)
PYTHONPATH=. python -m pytest tests/ -q                    # ~430 tests
PYTHONPATH=. python -m pytest tests/test_firmas.py -v      # cimática + firmas
PYTHONPATH=. python -m pytest tests/test_precursor.py -v   # precursor pipeline

# Sistema en vivo
python launcher.py                     # ciclo continuo (default 300s)
python launcher.py --once              # un ciclo y salir
python launcher.py --backcast          # carga histórica 1994-2025 (one-time)
python launcher.py --entrenar          # entrenamiento completo (3 fases + cimática)
python launcher.py --disciplina        # castigo desde abajo (M3.3-4.49)
python launcher.py --barrido           # compactación diaria + correlaciones + poda cimática
python shutdown.py                     # parar (SIGTERM, 30s → SIGKILL)
python reboot.py                       # stop + relaunch

# Juez / Reportes
python deploy/verificacion_juez.py
python deploy/generar_reporte.py
python deploy/reporte_ejecutivo.py
python deploy/reporte_periodico.py --comparativo
python deploy/enviar_correos.py

# Dashboard
streamlit run sentinel_omega/infrastructure/dashboard/app.py

# ===== PADRÓN DE AFILIADOS =====
cd /home/deamon/padron_afiliados_app

# Tests
python -m pytest tests/ -v

# Inicializar DB (si no existe)
python -c "
import sqlite3
conn = sqlite3.connect('database/padron.db')
with open('database/schema.sql') as f:
    conn.executescript(f.read())
conn.commit()
conn.close()
print('DB inicializada')
"

# Dashboard Streamlit
streamlit run src/app_afiliados.py

# Git (primera vez)
git add .
git commit -m "feat: v1.0.0 - Estructura inicial 11 tabs + analisis_comportamiento + tests"
git checkout -b local/padron-v1.0.0

# ===== CONCILIO (consensus-expert-agent) =====
cd /home/deamon/consensus-expert-agent
source .venv/bin/activate
python main.py --check                 # tiers + unload status
python main.py --task "…"              # pipeline secuencial (85%, max 3 rondas)
./run_telegram_bot.sh                  # TELEGRAM_* solo por .env
bash scripts/create_concilio_models.sh # concilio-worker / concilio-arbitro
```

---

## Estructura de Directorios

```text
/home/deamon/
├── README.md                    # Este archivo
├── CHANGELOG.md                 # Changelog combinado
├── AGENTS.md                    # Reglas para agentes
├── bridge/                      # DeamonX SSH/Ollama bridge (Termux)
├── docs/                        # Resúmenes de sesión / ops
├── workspaces/                  # PROD (último en preferencia)
│   └── sentinel_omega/          # Proyecto principal (git repo)
│       ├── sentinel_omega/      # Paquete Python (instalado editable)
│       ├── launcher.py          # Entry point
│       ├── orchestrator.py      # Orquestador (nivel raíz)
│       ├── tests/               # 430 tests
│       ├── data/                # DB + PID + logs (gitignored)
│       ├── .venv/               # Entorno virtual
│       ├── pyproject.toml
│       ├── CLAUDE.md
│       └── README.md
├── workspaces-dev/ / workspaces-test/   # Preferidos para Concilio / audits
├── consensus-expert-agent/      # Concilio (git repo independiente)
│   ├── engine/ orchestrator.py  # Pipeline secuencial + fast_ask
│   ├── agents/ memory/          # Roles + .concilio + anti-injection
│   ├── config.yaml              # inject_sentinel_architecture: false
│   ├── CONCILIO.md / AGENTS.md
│   ├── modelfiles/ scripts/
│   └── telegram_bot.py
├── padron_afiliados_app/        # Proyecto (git repo independiente)
│   ├── src/
│   │   ├── app_afiliados.py     # Streamlit 11 tabs
│   │   └── analisis_comportamiento.py
│   ├── database/
│   │   ├── schema.sql
│   │   └── padron.db
│   ├── tests/
│   │   └── test_analisis.py
│   ├── requirements.txt
│   ├── .gitignore
│   ├── venv/
│   ├── README.md
│   └── CHANGELOG.md
└── .venv/                       # Entorno virtual compartido (legacy)
```

---

## Variables de Entorno Requeridas

### Sentinel Omega
```bash
# .env en /home/deamon/workspaces/sentinel_omega/ o GitHub Secrets
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
SMTP_USER=xxx
SMTP_PASS=xxx
OPENWEATHERMAP_KEY=xxx
NASA_API_KEY=xxx
# EODAG para ESA Copernicus (opcional)
EODAG_USER=xxx
EODAG_PASSWORD=xxx
```

### Padrón de Afiliados
```bash
# .env en /home/deamon/padron_afiliados_app/
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

### Concilio (consensus-expert-agent)
```bash
# .env en /home/deamon/consensus-expert-agent/
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
# Nunca hardcodear; no volcar secretos en docs ni commits
```

---

## Despliegue y Servicios

### Sentinel Omega (systemd)
```bash
# Servicios instalados via deploy/install.sh
sudo systemctl enable sentinel-omega sentinel-omega-scheduler sentinel-omega-watchdog
sudo systemctl start sentinel-omega sentinel-omega-scheduler sentinel-omega-watchdog
sudo systemctl status sentinel-omega-watchdog  # Verificar watchdog activo
```

### Dashboard (ambos proyectos)
```bash
# Sentinel Omega
streamlit run /home/deamon/workspaces/sentinel_omega/sentinel_omega/infrastructure/dashboard/app.py --server.port 8501

# Padrón de Afiliados
streamlit run /home/deamon/padron_afiliados_app/src/app_afiliados.py --server.port 8502
```

---

## Notas para Agentes

1. **Contexto dual**: Al entrar, leer tanto `AGENTS.md` como el `CLAUDE.md` dentro de `sentinel_omega/` si vas a trabajar en ese proyecto.
2. **PYTHONPATH**: Para tests de sentinel_omega, **siempre** usar `PYTHONPATH=.` desde `/home/deamon/workspaces/sentinel_omega/`.
3. **Git isolation**: `padron_afiliados_app` tiene su propio `.git` — no mezclar con workspaces root.
4. **Ollama / Concilio**: bases `qwen2.5:1.5b` + `gemma4:26b`; aliases `concilio-worker`/`concilio-arbitro`. Umbral 85; un modelo a la vez; límites contexto ~8k / 2.5k/file / num_predict 800. Ver `/home/deamon/consensus-expert-agent/AGENTS.md`.
5. **Verificación**: REGLA CERO — nunca asumas, siempre verifica corriendo el flujo punta a punta.
6. **Concilio vs Sentinel**: `inject_sentinel_architecture: false` por defecto; no tocar DB prod ni systemd desde consensus-expert-agent.

---

## Rama `local/home-bridge`

Contenido del home de **deamon** orientado a puente móvil / bridge (WSL Kali ↔ Termux).

Ver también: `local/concilio`, `local/padron`, `local/sentinel-omega` en `Inzainos/Local`.
