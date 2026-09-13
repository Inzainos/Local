# AGENTS.md — Home Workspace (/home/deamon/)

Guía operativa para agentes de IA que trabajen en este workspace (Claude Code, Cursor, Copilot, Codex, etc.).  
Es el archivo neutral que leen todas las herramientas; cada proyecto tiene su propio detalle adicional:

- `workspaces/sentinel_omega/CLAUDE.md` — Detalle específico Sentinel Omega.
- `workspaces/sentinel_omega/README.md` — Descripción completa del proyecto Sentinel Omega.
- `padron_afiliados_app/README.md` — Descripción completa del proyecto Padrón de Afiliados.
- `consensus-expert-agent/AGENTS.md` — Reglas locales del Concilio (apunta de vuelta a este archivo).
- `consensus-expert-agent/CONCILIO.md` — Protocolo secuencial Ollama (85%, Telegram, anti-inyección).
- `bridge/TERMUX.md` — Puente DeamonX (Termux) → Ollama por SSH local-forward.
- `docs/DEAMONX_BRIDGE_2026-09-13.md` — Resumen ops puente 2026-09-13.

---

## Qué es este Workspace

Tres proyectos independientes en `/home/deamon/`:

### 1. Sentinel Omega (`/home/deamon/workspaces/sentinel_omega/`)
**Plataforma de detección de precursores de eventos naturales** (sismos, volcanes, tormentas solares, tsunamis).  
Autor: Elán Zainos Corona (Fractal Core Research). Sucesor de la familia TITAN V32/V46/V53.

**Alcance**: **Únicamente precursores de eventos naturales.** No mezclar aquí:
- Genómica → repo *SNT Genómica* (separado).
- Sentinel Titan (lotería / "Elite") → otra rama, no en `main`.
- De lo financiero, este repo **sí** usa bolsa, cripto y tendencias (bot `delta`, "el humor de la tierra") como una señal precursora más.

SNT (Shadow Node Theory) se usa **solo como framework matemático** (ley de potencia `R(t) = a·t^b`), no como propósito del sistema.

### 2. Padrón de Afiliados (`/home/deamon/padron_afiliados_app/`)
**Sistema de control electoral** — Dashboard Streamlit 11 pestañas + alertas Telegram con gráficas/tablas/cimática detallada.  
Análisis demográfico, participación electoral, cohortes, cimática (FFT/autocorrelación), redes de afiliados, detección de outliers.

### 3. Concilio — consensus-expert-agent (`/home/deamon/consensus-expert-agent/`)
**Pipeline secuencial multi-agente sobre Ollama** (consenso local + puente Telegram).

- Orden: lightest → medium → heavy → lightest verify; reentrada si score < **85**; máx. 3 rondas.
- Modelos: `concilio-worker` / `concilio-arbitro` (aliases lightest|medium|heavy); bases `qwen2.5:1.5b` + `gemma4:26b`.
- **`inject_sentinel_architecture: false`** por defecto (sin corpus Sentinel en cada run) hasta que terminen updates Sentinel en otro hilo.
- `.concilio` = DATA (anti-inyección). Fast Gente/Estado (`POST /api/ask`) **fuera** del Concilio.
- Relación con Sentinel: agente de consenso/auditoría; no toca DB prod ni systemd; preferir `workspaces-dev`.
- Docs: `AGENTS.md`, `CONCILIO.md`, `README.md`, stub `data/memory_packs/home_hard_rules_stub.md`.

**Relacionado (no es 4º proyecto independiente):** **DeamonX-Mobile** — nodo Termux (Honor X7d) en el ecosistema Concilio/Sentinel. Scripts host en `/home/deamon/bridge/`. Ver sección *DeamonX-Mobile + puente SSH* más abajo.


### Concilio / Telegram (ops 2026-09-13)

- `/task` = **ligero** (`fast_ask` + pack Sentinel thin). Eventos/precursores = DB Sentinel.
- `/concilio` = **heavy** (lightest->medium->heavy->verify, umbral 85). `/audit` inyecta Sentinel solo en esa corrida.
- Units: `consensus-telegram.service` + `consensus-web.service` (`:8002` Mini App local).
- **Ollama**: API `:11434` = **Windows** `ollama.exe` (auto con login). Unit Kali `ollama.service` = **disabled** (evita choque de puerto).
- Mini App en Telegram: `TELEGRAM_WEBAPP_URL` HTTPS via user-unit `cloudflared-mini` (`~/.config/systemd/user/`, Linger=yes). Local: `http://127.0.0.1:8002/mini`.
- DeamonX (movil): nodo LLM aparte; no duplicar `alert_queue`/bot TG.
- Detalle: `consensus-expert-agent/docs/FUNCIONAMIENTO_TELEGRAM.md` (v2.2.5+).


---

## Estructura de Alto Nivel

```text
/home/deamon/
├── README.md                    # Contexto unificado
├── CHANGELOG.md                 # Historial combinado
├── AGENTS.md                    # Este archivo
├── bridge/                      # DeamonX SSH bridge (Termux ↔ Ollama)
├── docs/                        # Resúmenes sesión / ops
├── workspaces/ / workspaces-dev/ / workspaces-test/
│   └── sentinel_omega/          # Proyecto principal (preferir DEV para Concilio)
│       ├── sentinel_omega/      # Paquete Python (instalado editable: pip list)
│       ├── launcher.py          # Entry point principal
│       ├── orchestrator.py      # Orquestador (nivel raíz, no en paquete)
│       ├── tests/               # 430 tests
│       ├── data/                # DB + PID + logs (gitignored)
│       ├── .venv/               # Entorno virtual dedicado
│       ├── pyproject.toml
│       ├── CLAUDE.md
│       └── README.md
├── consensus-expert-agent/      # Concilio (git repo independiente)
│   ├── engine/ agents/ memory/
│   ├── config.yaml              # inject_sentinel_architecture: false
│   ├── CONCILIO.md / AGENTS.md / README.md
│   ├── telegram_bot.py
│   └── modelfiles/ scripts/
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

## Comandos Principales

### Sentinel Omega
```bash
cd /home/deamon/workspaces/sentinel_omega

# Tests — SIEMPRE con PYTHONPATH=. desde la raíz del proyecto
PYTHONPATH=. python -m pytest tests/ -q              # ~430 tests
PYTHONPATH=. python -m pytest tests/test_firmas.py -v
PYTHONPATH=. python -m pytest tests/test_precursor.py -v

# Sistema en vivo
python launcher.py                     # ciclo continuo (default 300s)
python launcher.py --once              # un ciclo y salir
python launcher.py --backcast          # carga histórica 1994-2025 (one-time)
python launcher.py --entrenar          # entrenamiento completo (3 fases → cimática)
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
streamlit run sentinel_omega/infrastructure/dashboard/app.py --server.port 8501
```

### Padrón de Afiliados
```bash
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
streamlit run src/app_afiliados.py --server.port 8502

# Git (primera vez)
git add .
git commit -m "feat: v1.0.0 - Estructura inicial 11 tabs + analisis_comportamiento + tests"
git checkout -b local/padron-v1.0.0
```

### Concilio (consensus-expert-agent)
```bash
cd /home/deamon/consensus-expert-agent
source .venv/bin/activate
python main.py --check
python main.py --task "..."
./run_telegram_bot.sh
bash scripts/create_concilio_models.sh
```

---


## DeamonX-Mobile + puente SSH

Nodo móvil (**Agente-A**) en Honor X7d / Termux. Habla con X-Deamon solo por SSH; **no** es un cuarto proyecto con repo propio — vive en el ecosistema Concilio/Sentinel.

### Roles
| Código | Quién |
|--------|--------|
| **G** | Coordinación / sudo |
| **C** | Host / `sshd` / puente |
| **T** | Concilio / Telegram |
| **A** | DeamonX mobile |

### Reglas duras del puente
1. **Prohibido** `OLLAMA_HOST=0.0.0.0` o bind Ollama a la LAN sin OK explícito del operador.
2. Ollama runtime = Windows `ollama.exe`; en Kali `ollama.service` está **disabled**.
3. Acceso desde el teléfono: `ssh -N -L 11434:127.0.0.1:11434 deamon@<IP-LAN-host>`.
4. En Termux / `~/deamonx_mobile/config.env`:
   - `REMOTE_OLLAMA_URL=http://127.0.0.1:11434`
   - `REMOTE_MODEL=concilio-lightest:latest` (modelos **light** en móvil; heavy queda en host vía Concilio).
5. `sshd` pubkey-only (`bridge/sshd_deamonx.conf`); Wi-Fi Private + firewall WSL SSH 22; autostart Kali = tarea `WSL-Kali-Autostart`.

### Scripts y docs
- `/home/deamon/bridge/` — `TERMUX.md`, `check_bridge.sh`, `install_sshd.sh`, confs sshd.
- `/home/deamon/docs/DEAMONX_BRIDGE_2026-09-13.md` — resumen de sesión.

```bash
~/bridge/check_bridge.sh
```

---

## Reglas Duras (No Romper)

0. **REGLA CERO — Nunca asumas, siempre revisa.** No des nada por hecho ni por conectado sin verificarlo contra el código y, cuando toque, **corriendo el flujo de punta a punta** (no basta con que pasen los tests unitarios). Antes de decir "ya está", compruébalo: ¿la tabla se pobló?, ¿el reporte lee la sección?, ¿el script corre sin error de verdad? Si no lo verificaste, no lo afirmes — di qué falta por comprobar.

1. **Secretos solo por entorno.** Nunca hardcodear API keys/tokens. Usa `os.environ.get("NOMBRE", "")`. Los `.env` están en `.gitignore`; en CI van como GitHub Secrets.

2. **Cero datos sintéticos.** Faltante = `NULL`. LOCF solo desde registros reales. El TEC derivado se etiqueta como *derived*, nunca como dato de sensor.

3. **`data/` está en `.gitignore`** — no existe en un checkout limpio (GitHub Actions). Crea la carpeta antes de abrir archivos ahí (`Path(...).parent.mkdir(parents=True, exist_ok=True)`).

4. **Reportes versionados, no sobrescritos.** `estado/REPORTE.md` es el último; cada corte se guarda en `estado/historial/AAAA/MM/` con hora local (UTC-6).

5. **Migración de esquema forward-only.** Columnas nuevas vía `EXPECTED_COLUMNS` / `_migrate_add_missing_columns`; no borrar columnas.

6. **Los tests deben pasar** antes de commitear cambios de código.

7. **Git convention**: Ramas `local/<feature>-v<version>` (ej. `local/alertas-v2.5.3`, `local/padron-v1.0.0`). **Nunca push directo a `main`**.

8. **PYTHONPATH para Sentinel Omega**: Tests de sentinel_omega **requieren** `PYTHONPATH=.` porque `orchestrator.py` está en la raíz, no dentro del paquete `sentinel_omega/`.

---

## Arquitectura Sentinel Omega (Para Ubicarte Rápido)

### 6 Agentes + Padre + Juez

| Bot | Dominio | Entrenamiento | Familia |
|-----|---------|---------------|---------|
| `alfa1` | Clima espacial: Bz, viento solar, Kp, protones/electrones | 30 años | space_weather |
| `alfa2` | Satélites ESA Sentinel | 14 años | space_weather |
| `beta1` | Resonancia Schumann — **el latido**; todo se correlaciona contra él | 30 años | schumann_cymatics |
| `beta2` | Desgasificación volcánica / atmósfera (SO₂) | 14 años | schumann_cymatics |
| `delta` | Bolsa + cripto + tendencias | 10 años | financial_sentiment |
| `omega` | Ritmo cósmico: fase lunar/sicigias + Schumann + envolvente solar + acoplamiento Schumann↔mercado | 30 años | (independiente) |
| `padre` | Consenso jerárquico cruzado entre familias (aplica pesos) | — | geodynamic |

- **Familias**: `space_weather` (alfa1/alfa2), `schumann_cymatics` (beta1/beta2), `financial_sentiment` (delta).
- **Consenso**: ≥2 familias + ≥2 alertas + correlación Schumann > 0.3.
- **Validación Junior→Senior**: Alfa-2/Beta-2 degradados a WATCH @ 50% si Senior no confirma.
- **Pesos disciplinarios** (Juez): `pesos_bots` de BD — castigo hijo ×1 / Padre ×2; peso < 0.6 → demote a WATCH.
- **Omega dual-ask vs Córum**: 4 casos (Omega solo, Córum solo, ambos, ninguno).
- **Pérdida asimétrica**: `miss_penalty = 10.0` vs `false_alarm_penalty = 1.0` (10× más costoso perder evento real).

### Firmas / Cimática
- Memoria de patrones por bot de la ventana de 14 días previa a cada evento.
- Estados: `nueva → observada → recurrente → consolidada`; solo consolidadas son exigibles.
- Frecuencia 3 = alerta automática + envío foto `cimatica_bars` a Telegram.

### Entrenamiento (3 fases)
1. **Fase 1**: Reconocimiento sísmico (sin castigo).
2. **Fase 1b**: Reconocimiento no sísmico (erupciones VEI≥3 + tormentas solares Kp≥6).
3. **Fase 2**: Disciplina (Padre castiga; Juez audita con severidad asimétrica).
4. Post-fases: Matriz correlaciones feature × event_class + sesgo aprendizaje (antes/después).

---

## Fuentes de Datos (Sentinel Omega)

Todas públicas salvo donde se indica:
- NOAA SWPC · USGS FDSN · NASA OMNI2 (backcast) · NASA MSVOLSO2L4 (SO₂ volcánico)
- Tomsk (Schumann) · IERS (LOD) · Yahoo Finance (BTC, keyless)
- OpenWeatherMap (`OPENWEATHERMAP_KEY`) · NASA NEO (`NASA_API_KEY`, fallback DEMO_KEY)
- ESA Copernicus vía eodag (`EODAG_USER`/`EODAG_PASSWORD`)

---

## Alertas y Reportes (Sentinel Omega)

**Canales**: Email (outbox `tbl_correo_salida`, fail-soft) + Telegram (enriquecido v2.5.3).

**Rutinas del vigilante (hora MX = UTC-6)**:
- Ciclo del Padre cada 2h
- Juez verifica real vs predicción cada 4h
- Reporte ejecutivo cada 6h
- Comparativo diario 12am/12pm
- Semanal domingo 12:15pm
- Mensual fin de mes 12:30pm

**Cimática** (`tbl_cimatica_patrones`): Snapshot telemetría por ciclo; patrón nuevo guarda todo, repetido suma +1 frecuencia; cualquier alta/incremento dispara revisión Padre → alerta si amerita.

---

## Variables de Entorno Requeridas

### Sentinel Omega (`.env` en `/home/deamon/workspaces/sentinel_omega/`)
```bash
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
SMTP_USER=xxx
SMTP_PASS=xxx
OPENWEATHERMAP_KEY=xxx
NASA_API_KEY=xxx
EODAG_USER=xxx
EODAG_PASSWORD=xxx
```

### Padrón de Afiliados (`.env` en `/home/deamon/padron_afiliados_app/`)
```bash
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

### Concilio (`.env` en `/home/deamon/consensus-expert-agent/`)
```bash
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

---

## Despliegue y Servicios (Sentinel Omega)

```bash
# Servicios systemd (instalados via deploy/install.sh)
sudo systemctl enable sentinel-omega sentinel-omega-scheduler sentinel-omega-watchdog
sudo systemctl start sentinel-omega sentinel-omega-scheduler sentinel-omega-watchdog
sudo systemctl status sentinel-omega-watchdog  # Verificar watchdog activo
```

**Watchdog** (`infrastructure/watchdog/network_watchdog.py`):
- Intervalo: 60s (`WATCHDOG_INTERVAL_S`)
- Umbral: 3 fallos consecutivos (`WATCHDOG_FAIL_THRESHOLD`)
- Checks: DNS TCP (8.8.8.8:53, 1.1.1.1:53) + HTTP (google, nasa)
- Health: `agent_bridge.agent_health()` → `db_exists` OR `ollama_ok`
- Acción: `systemctl restart sentinel-omega` + `sentinel-omega-scheduler` (+ dashboard si está)
- Notificación: `AlertService` → Telegram + Log (Severity.AMARILLO)

---

## Notas para Agentes

1. **Contexto dual**: Al entrar, leer tanto este `AGENTS.md` como el `CLAUDE.md` dentro de `sentinel_omega/` si vas a trabajar en ese proyecto.

2. **PYTHONPATH obligatorio**: Para tests de sentinel_omega, **siempre** usar `PYTHONPATH=.` desde `/home/deamon/workspaces/sentinel_omega/`.

3. **Git isolation**: `padron_afiliados_app` y `consensus-expert-agent` tienen su propio `.git` — no mezclar con workspaces root (`/home/deamon/workspaces/.git`).

4. **Ollama / Concilio**: bases `qwen2.5:1.5b` + `gemma4:26b`; aliases `concilio-worker`/`concilio-arbitro` (lightest|medium|heavy). Umbral **85**; un modelo a la vez; `.concilio` = DATA. Límites ~8k chars / 2.5k/file / `num_predict 800`. Guía: `consensus-expert-agent/AGENTS.md` + `CONCILIO.md`.

5. **Verificación**: REGLA CERO — nunca asumas, siempre verifica corriendo el flujo punta a punta.

6. **Proyecto activo**: Por defecto, **Sentinel Omega** es el proyecto principal. `padron_afiliados_app` está en fase esqueleto (v1.0.0). **Concilio** (`consensus-expert-agent`) es el consenso Ollama standalone (v2.2.1 thin; inject Sentinel off).

7. **Tests sentinel_omega**: 430 tests. Si falla `test_infrastructure.py` por import `orchestrator`, usar `from orchestrator import` (nivel raíz) no `from sentinel_omega.orchestrator import`.

8. **Concilio / Sentinel**: no tocar DB prod ni systemd desde consensus-expert-agent; `inject_sentinel_architecture: false` hasta updates Sentinel; preferir `workspaces-dev` si algún día se activa inject.

9. **DeamonX-Mobile**: puente en `/home/deamon/bridge/`; nunca abrir Ollama a LAN; usar túnel `-L 11434` y `concilio-lightest:latest` en el teléfono. Detalle: sección *DeamonX-Mobile + puente SSH* + `docs/DEAMONX_BRIDGE_2026-09-13.md`.
