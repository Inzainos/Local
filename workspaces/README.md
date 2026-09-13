# Workspaces

Repositorio base para **todos los proyectos** del workspace.  
Actualmente contiene como proyecto principal **Sentinel Omega** y su operación
completa (código, despliegue, reportes y automatizaciones).


## Estado reciente (2026-09-03)

Sesión de cableado para llevar el pipeline a operación completa:

| Área | Qué quedó |
|------|-----------|
| **Schema v11** | `tbl_locf_cache`, `tbl_eventos_catalogo`, DDL self-expanding (`schema_parts/`) |
| **LOCF** | Último valor real en DB si falla la API (cero sintéticos) |
| **ONNX** | Modelos + mixin para alfa1/2, beta1/2, delta, omega; train desde DB + Juez |
| **Juez 2h** | Ritmo cada 2 h; castigo/refuerzo a **todos** los bots (`juez_cycle_register`) |
| **Launcher** | Self-expanding desde `launcher_hex/`; `ventana_h` adaptativa (no 72 h fijas) |
| **Omega** | Dual-ask + puerta de referencia por asertividad |
| **Telegram** | Centinela V2 con gate 30 min y credenciales solo por env |
| **Volcado 24h** | Telemetría viva → histórico en cascada |
| **Dashboard** | Pestañas Alfas / Betas / Omega / Padre / Juez / Eventos / **Agente** (consenso) |
| **Mensajeria** | **AlertService** unificado (Telegram/Correo/Log) + **ReportEngine** versionado |
| **Agente** | consensus-expert-agent umbral 85/100, contexto inyectado, modo --audit |

Detalle en [`CHANGELOG.md`](CHANGELOG.md) → **[Unreleased] — 2026-08-19**.

```bash
git pull origin main
# verificar expansión del launcher
python -c "import pathlib,zlib; p=pathlib.Path('sentinel_omega/launcher_hex'); h=''.join(x.read_text().strip() for x in sorted(p.glob('h*.hex'))); s=zlib.decompress(bytes.fromhex(h)).decode(); assert 'register_cycle_predictions' in s; print('launcher OK', len(s))"
```

## Reglas operativas (AGENTS.md)

Este repositorio usa las reglas de `AGENTS.md` como guía central para agentes y
colaboradores. Puntos clave:

- Secretos solo por variables de entorno (nunca hardcodeados).
- Cero datos sintéticos: faltantes como `NULL` y datos derivados etiquetados.
- `sentinel_omega/data/` no se versiona y puede no existir en entornos limpios.
- Reportes versionados en `estado/historial/` (no sobrescribir historial).
- Migraciones de esquema solo forward-only.
- Antes de commitear cambios de código, los tests deben pasar.

## Estructura actual del repositorio

```text
workspaces/
├── AGENTS.md
├── CHANGELOG.md
├── LICENSE
├── README.md
├── .github/
│   └── workflows/
│       ├── bandit.yml
│       ├── codeql.yml
│       ├── copy-delta-to-snt.yml
│       └── roy-vigilante.yml
├── deploy/
│   ├── .env.example
│   ├── ATAJO_IOS.md
│   ├── DEPLOY.md
│   ├── generar_reporte.py
│   ├── install.sh
│   ├── run_windows.bat
│   ├── sentinel-omega-dashboard.service
│   └── sentinel-omega.service
├── estado/
│   ├── REPORTE.md
│   └── historial/
│       └── 2026/
├── sentinel_omega/
│   ├── CLAUDE.md
│   ├── README.md
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── launcher.py
│   ├── reboot.py
│   ├── shutdown.py
│   ├── orchestrator.py
│   ├── config/
│   ├── core/
│   ├── docs/
│   ├── infrastructure/
│   │   ├── messaging/       # AlertService + agent_bridge (unificado)
│   │   ├── pipeline/        # reporte_sentinel + ReportEngine
│   │   └── dashboard/       # app.py + agent_tab (pestana Agente)
│   ├── layers/
│   ├── models/
│   ├── notebooks/
│   └── tests/
└── staging/
```

## Qué contiene hoy

- Plataforma Sentinel Omega para detección de precursores de eventos naturales.
- Pipeline de adquisición/procesamiento, entrenamiento y consenso multiagente.
- **Entrenamiento multi-evento** (Fase 1b): sísmico + volcánico + solar + financiero.
- **delta_enriched**: acoplamiento geofísico-financiero (cross-correlation crypto/BTC).
- **Omega bot**: memoria del ritmo cósmico (luna, Schumann, correlaciones históricas).
- Scripts de despliegue local/servidor, dashboard y rebuild completo.
- Publicación y versionado de reportes operativos.
- Workflows de seguridad, análisis y ejecución automática en GitHub Actions.

## Rebuild Completo

Para reconstruir la base de datos con entrenamiento de punta a punta:

```bash
# En server con virtualenv activado:
nohup python deploy/rebuild_completo.py > estado/rebuild.log 2>&1 &
```

El script:
1. Para launcher activo
2. Vacía memoria aprendida (conserva backcast + fase viva del Juez)
3. Migración DB v6 + índices + vistas
4. Tuning (ANALYZE + PRAGMA optimize)
5. Entrenamiento: Fase 1 + 1b (multi-evento) + Fase 2 + lags + correlaciones
6. Disciplina de trasfondo + barrido diario
7. VACUUM + compactación
8. Genera reportes (REPORTE.md + REPORTE_EJECUTIVO.md)

Reporte final en `estado/REPORTE_REBUILD.md`.
