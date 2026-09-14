# Local

Índice de los **proyectos locales de la Catana** (máquina Kali / WSL, host `deamon` / `X-Deamon`).

Aquí vive **exclusivamente** lo que tengo en la Catana y decido subir a GitHub. Nada más.
`main` contiene **solo este índice + `LICENSE`**; el código de cada sistema vive en su propia
rama huérfana (raíz limpia e historia independiente por sistema).

## Qué es este repositorio (y qué no)

- **Es:** un catálogo/punto de entrada a los sistemas que corro localmente en la Catana.
  Cada sistema es una rama `local/*` con su propio `README.md` y `AGENTS.md`, sin secretos
  (`.env`, DBs, modelos ONNX y `venv` quedan fuera).
- **No es:** un monorepo con historia compartida. Las ramas no se mezclan entre sí; `main`
  nunca contiene código de los sistemas.

## Relación con otros repositorios

Este repo es **el índice de lo local de la Catana**. Los proyectos que tienen su propio
repositorio independiente **no** viven aquí; solo se referencian para dejar clara la diferencia:

- **Sentinel Ω** — su **primera versión** (los `workspaces`) sí vive aquí, en la rama
  `local/sentinel-omega`. Las iteraciones posteriores, si tienen repo propio, van aparte.
- **Shadow Note Theory** — proyecto con su **propio repositorio**, fuera de este índice.

> La tabla de sistemas de abajo se genera sola desde las ramas reales del remoto. No la edites
> a mano.

<!-- BEGIN:AUTO-INDEX -->

> Tabla generada automaticamente por `tools/gen_index.py` desde las ramas reales del remoto. No la edites a mano: modifica `tools/systems.json` y vuelve a ejecutar el generador (la fecha de cada corrida queda en `logs/gen_index.log`).

### Sistemas (`local/*`)

| Rama | Sistema | Origen local | SHA |
|------|---------|--------------|-----|
| `local/concilio` | Consensus / Concilio expert agent | `/home/deamon/consensus-expert-agent` | `c11df3f` |
| `local/concilio-2.2.6-20260913` | Consensus / Concilio expert agent (snapshot v2.2.6, 2026-09-13) | `/home/deamon/consensus-expert-agent` | `f4abb65` |
| `local/deamonx-bridge-v1.0.0` | DeamonX bridge (release v1.0.0) | `/home/deamon/bridge` | `562634e` |
| `local/home-bridge` | Home bridge / DeamonX movil | `/home/deamon (README, AGENTS, CHANGELOG, bridge/, docs DeamonX)` | `b80548b` |
| `local/padron` | Padron de afiliados (Streamlit) | `/home/deamon/padron_afiliados_app` | `49caaac` |
| `local/sentinel-omega` | Sentinel Ω — primera version (workspaces) | `/home/deamon/workspaces (sin ONNX/DB/.env/venv)` | `8ed0681` |
| `local/watchdog` | Watchdog / monitor local | `/home/deamon (watchdog)` | `358f2ee` |

### Ramas de revision / efimeras (`review/*`, `wip/*`)

- `review/sentinel-base-b639aa8` (`b639aa8`) — temporal; no es un sistema publicado.

### Uso rapido

```bash
git clone -b local/concilio https://github.com/Inzainos/Local Local-concilio
git clone -b local/concilio-2.2.6-20260913 https://github.com/Inzainos/Local Local-concilio-2.2.6-20260913
git clone -b local/deamonx-bridge-v1.0.0 https://github.com/Inzainos/Local Local-deamonx-bridge-v1.0.0
git clone -b local/home-bridge https://github.com/Inzainos/Local Local-home-bridge
git clone -b local/padron https://github.com/Inzainos/Local Local-padron
git clone -b local/sentinel-omega https://github.com/Inzainos/Local Local-sentinel-omega
git clone -b local/watchdog https://github.com/Inzainos/Local Local-watchdog
```

<!-- END:AUTO-INDEX -->

## Cómo se mantiene el índice

La sección entre los marcadores `AUTO-INDEX` la produce `tools/gen_index.py`, que lee las
ramas reales con `git ls-remote` y las clasifica:

| Prefijo de rama | Va en |
|-----------------|-------|
| `local/*` | Tabla de sistemas |
| `review/*`, `wip/*` | Lista de ramas de revisión / efímeras |
| `main`, `claude/*` | Infraestructura (se ignora en el índice) |

```bash
# Regenerar el índice en el sitio
python3 tools/gen_index.py

# Solo verificar (CI): sale con código 1 si el README está desfasado
python3 tools/gen_index.py --check
```

Las descripciones de cada sistema (columnas *Sistema* y *Origen local*) se editan en
[`tools/systems.json`](tools/systems.json). Una rama `local/*` sin entrada ahí se lista igual,
con la descripción marcada como pendiente. Cada ejecución deja registro en `logs/gen_index.log`.

El workflow [`.github/workflows/index.yml`](.github/workflows/index.yml) regenera y commitea el
índice automáticamente (al crear ramas, en cada push a `main`, a diario y bajo demanda), y en los
pull requests solo verifica con `--check`.
