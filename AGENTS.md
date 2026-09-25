# AGENTS.md — consensus-expert-agent (Concilio) · v1

Guía local para agentes que trabajen en `/home/deamon/consensus-expert-agent/`.

**Leer primero el home:** [`/home/deamon/AGENTS.md`](../AGENTS.md) — reglas duras del workspace,
mapa Sentinel Omega + Padrón + Concilio, secretos, git, workspace roots.

Este archivo sólo añade reglas **locales del Concilio**. No reemplaza el home AGENTS.

---

## Qué es este proyecto (v1, 2026-09-25)

Resolver tareas con modelos **locales** (Ollama) y **comprobar el resultado ejecutándolo**, no
leyéndolo. Todo entra por `engine/orchestrator.py::run_consensus` (bot, CLI, web y `main.py`):

```
tarea de código con una función nombrada
  └─ VÍA DIRECTA: el coder escribe la función (una llamada, temperatura 0)
       └─ VERIFICADOR: la ejecuta contra casos
            ├─ casos construidos desde la especificación y TODOS pasan → VERIFICADO, se entrega
            ├─ falla con casos fiables → 2.º intento con los casos fallidos → si falla, CONCILIO
            └─ el enunciado no admite casos fiables → se entrega rotulado SIN VERIFICAR
tarea de investigación / análisis, o sin función nombrada
  └─ CONCILIO: investigador → coder → árbitro + verificador, con frenos de estancamiento
```

**Por qué la vía directa:** medido el 2026-09-25, codegemma resolvió 6/7 tareas a la primera en
~30 s; el concilio tardó 25–50 min por tarea y no cerró ninguna. Ver `CHANGELOG.md`.

### Modelos y por qué (todo medido; no cambiar sin volver a medir)

| rol | modelo | ventana | por qué |
|---|---|---|---|
| coder | `codegemma:7b` (respaldo `qwen2.5-coder:7b`) | 8.192 (su máximo) | 6/7 tareas, 72/73 casos a la primera; qwen 5/7, 60/73 |
| extractor de formato | `qwen2.5-coder:7b` | 4.096 | el único de 5 que extrajo bien la especificación del token |
| investigador | `concilio-investigador` (llama3.2:3b) | 16.384 | |
| árbitro | `concilio-arbitro` (gemma3:4b) | 16.384 | su lectura NO decide si el código funciona |
| portero (v2) | `nemotron-mini` | 4.096 | **sólo** portero, por decisión del operador |
| segmentador | desactivado | — | empeoraba al coder (72→68/73), ver `config.yaml` |

`deepseek-r1:8b` (`concilio-medium`) es modelo de razonamiento: se gastó 15 min pensando sin
escribir la función. Queda en los niveles de la v2. `deepseek-r1:14b` **no cabe** en esta máquina.

---

## Reglas locales del Concilio (además del home)

1. **Un modelo cargado a la vez.** Toda precarga pasa `num_ctx`: el servidor tiene
   `OLLAMA_CONTEXT_LENGTH=262144` y sin ventana reserva caché para esa cifra. El techo útil por
   modelo con Sentinel corriendo es ~7,3 GiB (host 11,71 GiB; medido con `Win32_OperatingSystem`,
   **no** con `free` de WSL, que no ve el host).
2. **Nada se aprueba por lectura.** La puntuación del árbitro leyendo puso 92–99 a código que
   rechazaba todos los casos válidos. Con casos de **especificación**, se exigen **todos**; los
   casos **derivados** por un modelo nunca aprueban (fallan en las dos direcciones). El umbral
   85 sólo rige lo que no se puede ejecutar.
3. **No** forzar inyección de arquitectura Sentinel mientras `inject_sentinel_architecture: false`.
4. Stub opcional (no auto): `data/memory_packs/home_hard_rules_stub.md`.
5. Pack completo Sentinel sólo si se activa inject (y preferir `workspaces-dev`).
6. **No** tocar DB prod de Sentinel Omega ni systemd desde este repo.
7. **No** volcar ni commitear secretos `.env`.
8. No lanzar tareas Ollama largas sin orden explícita del operador.
9. Preferir Modelfiles thin (`modelfiles/`) sobre corpus embebido.
10. **La memoria sólo archiva consenso real** (`consensus_reached`), y cada antecedente inyectado
    pasa por un filtro de relevancia. Los 7 hechos aprobados antes del verificador están en
    `knowledge_facts_cuarentena`, no borrados.

---

## Cómo verificar un cambio

- Pruebas con **el intérprete del entorno**: `.venv/bin/python -m pytest tests/ -q -rs`. Con
  `/usr/bin/python3` el guardián de pyflakes no puede correr (y ahora falla en vez de pasar vacío).
- **Cero tests saltados**: un test saltado pasa sin probar nada.
- Validar cada arreglo **por mutación**: revertirlo y comprobar que su test cae.
- **Barrido de hermanos**: si se arregla un defecto en un sitio, buscar el mismo patrón en los
  demás (selección de modelos, llamadas a Ollama, entradas: bot, CLI, web, `main.py`). En la v1
  esto encontró seis sitios con la versión vieja (selección del coder, `fast_ask`, huella del
  freno, insignia de la web, test de huella en f16, cartel del CLI).
- Importar de verdad los módulos tocados: pyflakes no detecta imports rotos.

---

## Comandos útiles

```bash
cd /home/deamon/consensus-expert-agent
.venv/bin/python -m pytest tests/ -q -rs      # siempre con el intérprete del entorno
.venv/bin/python main.py --check               # Ollama y modelos
.venv/bin/python main.py --task "…"            # vía directa → concilio si hace falta
.venv/bin/python main.py --web                 # interfaz web
./run_telegram_bot.sh                          # requiere TELEGRAM_* en .env
bash scripts/create_concilio_models.sh         # Modelfiles thin
```

Ollama corre con caché KV `q8_0` + flash attention (variables de usuario de Windows,
verificadas en el log de arranque del servidor). Para revertir:
`C:\Users\elanz\AppData\Local\Temp\ollama_revertir.ps1`.

---

## Qué NO hace la v1 (queda para la v2)

- **Investigación y análisis no se verifican**: no hay nada que ejecutar. La independencia de
  los modelos está resuelta para código, no para investigación.
- Tareas de código que no son validadores de formato se entregan **sin verificar**: falta la
  «opción C» (relaciones sin oráculo, p. ej. `f('1h30m') == f('1h') + f('30m')`).
- Motor de turnos + niveles + portero (`engine/turnos*.py`, `profiles/niveles.yaml`): escritos y
  probados, **no cableados**.
- Índice vectorial con `nomic-embed-text`: el filtro de relevancia actual es léxico.

Las tuberías anteriores (`run_moe`, `run_profile`) están retiradas en [`legacy/`](./legacy/README.md).

---

## Relación con Sentinel Omega

Concilio es el agente de consenso/auditoría local. La integración de arquitectura Sentinel
queda **opt-in** vía `concilio.inject_sentinel_architecture: true`. Sentinel sólo consulta la
salud de Ollama (`/api/tags`); no le pide inferencias.

Detalle operativo: [`CONCILIO.md`](./CONCILIO.md). Changelog: [`CHANGELOG.md`](./CHANGELOG.md).
