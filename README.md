# Sentinel Ω — detección de precursores de eventos naturales

Rama del monorepo [`Inzainos/Local`](https://github.com/Inzainos/Local). Ver también
`local/home-bridge`, `local/concilio`, `local/padron` y `local/watchdog`.

Origen local: `/home/deamon/workspaces` en WSL2 Kali (**deamon** / X-Deamon).
Autor: Elán Zainos Corona (Fractal Core Research). Sucesor de la familia TITAN V32/V46/V53.

## Qué es

Plataforma de detección de **precursores de eventos naturales** (sismos, actividad
volcánica, tormentas solares, tsunamis). Seis agentes + Padre árbitro + Juez auditor,
con pipeline continuo, base de datos propia, reportes versionados y dashboard.

| Bot | Dominio | Entrenamiento |
|-----|---------|---------------|
| `alfa1` | Clima espacial: Bz, viento solar, Kp, protones/electrones | 30 años |
| `beta1` | Resonancia Schumann — el latido; todo se correlaciona contra él | 30 años |
| `alfa2` | Satélites ESA Sentinel | 14 años |
| `beta2` | Desgasificación volcánica / atmósfera (SO₂ sobre baseline natural) | 14 años |
| `delta` | Bolsa + cripto + tendencias | 10 años |
| `omega` | Ritmo cósmico: fase lunar/sicigias + Schumann + envolvente solar | 30 años |
| `padre` | Consenso jerárquico cruzado entre familias | — |
| `juez` | Auditor: castigo/refuerzo a todos los bots. Nunca predice | — |

Detalle completo: [`workspaces/README.md`](workspaces/README.md).
Reglas para agentes de IA: [`AGENTS.md`](AGENTS.md) y `workspaces/sentinel_omega/CLAUDE.md`.

## Estructura

```
workspaces/
├── sentinel_omega/      El sistema: 6 agentes + Padre + Juez, pipeline, DB, dashboard
├── deploy/              Operación: reportes, systemd/Windows, atajo iOS, .env.example
├── estado/              Reportes publicados + historial/AAAA/MM/
├── database/            schema.sql
└── .github/workflows/   bandit, codeql, copy-delta-to-snt, roy-vigilante
```

## Comandos

```bash
# Tests — SIEMPRE desde la raíz del workspace, nunca desde dentro de sentinel_omega/
python -m pytest sentinel_omega/tests/ -q

# Sistema en vivo
python sentinel_omega/launcher.py            # ciclo continuo (default 300s)
python sentinel_omega/launcher.py --once     # un ciclo y salir
python sentinel_omega/shutdown.py            # parar (SIGTERM, 30s → SIGKILL)

# Reportes y dashboard
python deploy/generar_reporte.py
streamlit run sentinel_omega/infrastructure/dashboard/app.py
```

## Notas de estructura (verificado 2026-09-13)

Tres puntos que confunden al leer el árbol por primera vez. Se documentan tal cual
están; no se han modificado.

**1. Hay dos directorios `models/`.** El canónico es
`workspaces/sentinel_omega/models/`:

- Su `models_meta.json` marca `retrained_at` **2026-09-13T09:05Z** y muestras
  mayores (alfa1 n=1388, beta1 n=2082, omega n=2726).
- El anidado `workspaces/sentinel_omega/sentinel_omega/models/` marca
  **2026-09-11T00:20Z** y muestras menores (alfa1 n=1303, beta1 n=1997, omega n=2556).
- El campo `path` de **ambos** meta apunta al mismo destino absoluto,
  `/home/deamon/workspaces/sentinel_omega/models/`: incluso el entrenamiento que
  generó la copia anidada escribió en el directorio de primer nivel.
- Coincide con `config/onnx_config.py → get_full_path()`, cuyo `base_dir` por
  defecto es `sentinel_omega/models` relativo al CWD (`/home/deamon/workspaces`).

El anidado es una copia congelada del 2026-09-11. Los dos `onnx_config.py` son
idénticos byte a byte; el árbol anidado tiene 205 archivos contra 282 del de
primer nivel.

**2. Los workflows no se ejecutan.** Viven en `workspaces/.github/workflows/`.
GitHub solo lee `.github/workflows/` en la raíz del repositorio, así que hoy
ninguno de los cuatro corre. Además los `schedule:` solo disparan desde la rama
por defecto del repo (`main`), y esta es una rama huérfana.

**3. Symlink roto en checkout limpio.**
`workspaces/.agents/skills/developing-with-streamlit` apunta dentro de `.venv/`,
que está en `.gitignore`. Queda colgando hasta crear el entorno con Streamlit
instalado. (`workspaces/sentinel_omega/sentinel_omega/data → ../data` sí resuelve.)

**4. Licencia inconsistente.** El `LICENSE` de raíz es MIT (heredado del monorepo),
mientras que `workspaces/sentinel_omega/pyproject.toml` declara
`Proprietary — Fractal Core Research`. Pendiente de resolver por el autor.

## Qué se versiona y qué no

Se versionan los modelos `.onnx` entrenados (14 archivos, ~780 KB el mayor) porque
el pipeline los carga directo del árbol. **No** se versionan: `.env`, bases de datos
binarias, `venv/`/`.venv/` ni `sentinel_omega/data/` — este último no existe en un
checkout limpio, así que todo código que escriba ahí debe crear la carpeta primero.
