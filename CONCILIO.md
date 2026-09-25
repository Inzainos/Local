# Sequential Concilio

> **Desde la v1 (2026-09-25) el concilio es la SEGUNDA vía.** Las tareas de código con una
> función nombrada pasan primero por la **vía directa** (una llamada al coder + verificación por
> ejecución, ver [`AGENTS.md`](./AGENTS.md)); el concilio entra si esa vía no verifica, y para
> investigación y análisis.

## Qué es

Pipeline multi-agente **secuencial** sobre Ollama:

1. **Un solo modelo residente** a la vez (VRAM).
2. Ciclo por etapa: **load → run → write `data/sessions/<id>.concilio` → unload → next**.
3. Orden: **LIGHTEST → MEDIUM → HEAVY → LIGHTEST verify**.
4. `concilio-investigador` (llama3.2:3b) hace RESEARCH; `codegemma:7b` hace CODING/REFINING (elegido midiendo: 6/7 tareas a la primera).
5. Árbitro (`gemma3:4b` / `concilio-arbitro` / heavy) hace REVIEW + SYNTHESIS.
6. **El código se verifica EJECUTÁNDOLO** (`engine/verificador.py`): con casos construidos desde la especificación se exigen todos; los derivados por un modelo nunca aprueban. El umbral **85** sólo rige lo que no se puede ejecutar. Sin tope fijo de rondas: paran los frenos (entregable idéntico, o 4 rondas sin mejorar por encima del ruido σ 6,9).
7. El contenido de `.concilio` se inyecta **fenced como DATA**, nunca como instrucciones.
8. **`inject_sentinel_architecture: false`** por defecto — sin corpus de arquitectura Sentinel en cada run.
9. **Fast Gente/Estado** (`POST /api/ask`, `ConsensusOrchestrator.fast_ask`) queda **fuera** del Concilio.

Guía de agentes: [`AGENTS.md`](./AGENTS.md) (apunta a `/home/deamon/AGENTS.md`).

## Archivos clave

| Path | Rol |
|------|-----|
| `engine/orchestrator.py` | Vía directa + orquestación secuencial + `fast_ask` |
| `engine/verificador.py` | Ejecuta la solución contra casos derivados DEL ENUNCIADO; extrae el código a ejecutar |
| `engine/especificacion.py` | El modelo extrae el formato; Python construye los casos de frontera |
| `engine/segmentacion.py` | Tarea / reglas / límites (desactivado en la v1: empeoraba al coder) |
| `engine/turnos.py`, `engine/turnos_ollama.py` | Motor de turnos por niveles + capitán (v2, no cableado) |
| `engine/model_lifecycle.py` | warm / stop (`keep_alive=0`) |
| `memory/concilio_store.py` | `data/sessions/<id>.concilio` |
| `memory/shared_context.py` | Memoria entre sesiones (antecedentes + hechos) |
| `memory/persistent_store.py` | SQLite: `blackboard_snapshots`, `knowledge_facts` |
| `memory/anti_injection.py` | Fences + strip de jailbreaks |
| `memory/memory_pack.py` | Pack desde docs DEV (sin `.env`) — solo si inject=true |
| `data/memory_packs/home_hard_rules_stub.md` | Stub thin opcional (home hard rules) |
| `modelfiles/Modelfile.*` | Custom Ollama models (thin / aliases) |
| `scripts/create_concilio_models.sh` | `ollama create` |
| `config.yaml` | Comentarios de reglas home + concilio.* |

## Crear modelos Ollama

```bash
cd /home/deamon/consensus-expert-agent
./scripts/create_concilio_models.sh
```

Requiere bases: `codegemma:7b`, `qwen2.5-coder:7b`, `gemma3:4b`, `llama3.2:3b`. (`nemotron-mini` sólo para el portero de la v2.)

## Config (`config.yaml`)

```yaml
consensus:
  threshold_score: 85            # sólo para lo que no se puede ejecutar
  max_refinement_rounds: 0       # sin tope: paran los frenos
  rondas_sin_mejora_para_parar: 4
concilio:
  sequential: true
  inject_sentinel_architecture: false
  sessions_dir: data/sessions
  worker_model: concilio-investigador
  coder_model: codegemma:7b
  arbiter_model: concilio-arbitro
  extractor_formato: qwen2.5-coder:7b
  via_directa: true
  verify_with_light: true
  hard_rules_stub: data/memory_packs/home_hard_rules_stub.md
```

El modelo **configurado** gana siempre a las listas de preferencia internas (antes una lista fija lo pisaba en silencio). Si un `concilio-*` no está en `ollama list`, cae a `llama3.2:3b` / `gemma3:4b`.
Con `inject_sentinel_architecture: false` prioriza tags `concilio-*` sobre `sentinel-concilio-*`.

## Hard rules del home (honrar; no forzar pack)

Ver comentarios en `config.yaml` y stub `home_hard_rules_stub.md`:

- Secretos solo por env; cero sintéticos; `data/` gitignored + mkdir
- Workspace roots: DEV → TEST → PROD; no DB prod / systemd
- Telegram solo por env; git `local/<feature>-vX`; umbral 85
- REGLA CERO: verificar punta a punta

## Memoria entre sesiones

El Concilio arranca con dos clases de antecedente, inyectadas en
`research_context` (lo que ya leen Researcher, Coder y Optimizer):

| Qué | De dónde | Contenido |
|---|---|---|
| Tareas previas | `blackboard_snapshots` | Enunciado + score + veredicto. Sin contenido. |
| Hechos aprobados | `knowledge_facts` | Enunciado + síntesis (400 chars). |

**Criterio de archivo: sólo se recuerda un consenso REAL** (`consensus_reached`), no una
puntuación que cruce el umbral: una ronda bloqueada por no poder ejecutarse conserva su nota de
lectura y antes se archivaba. Los 7 hechos aprobados antes del verificador están en
`knowledge_facts_cuarentena`. **Cada antecedente y cada hecho pasa por un filtro de relevancia**
(idf sobre los propios antecedentes): antes se inyectaban los 5 más recientes y una tarea de
tokens recibía el enunciado de un palíndromo.

Criterio original, que sigue en pie: sólo se recuerda lo que superó el umbral. Una
síntesis reprobada es un borrador; archivarla contaminaría las tareas
siguientes con material que el propio sistema rechazó. Se compara contra
el umbral registrado en la pizarra (`consensus_threshold`), nunca contra
un 85 escrito en el código: si `config.yaml` cambia, cada tarea sigue
juzgada por la barra de su momento. Sin umbral registrado no se archiva
nada — ausencia de dato no es permiso.

Todo el bloque va cercado con `fence_untrusted(role="historial_tareas")`.
Las síntesis pasadas son **salida de modelo**, no entrada del operador:
un intento de inyección archivado en una tarea vieja no puede dar
órdenes en una nueva. Y un hecho aprobado sigue siendo dato a verificar,
no verdad establecida — el Concilio no debe tratar su propio pasado como
autoridad.

### Rondas: dos contadores distintos

| Campo | Cuenta |
|---|---|
| `concilio_rounds` | Reentradas completas `light→medium→heavy→verify`. Vale para cualquier tarea. |
| `refinement_rounds` | Solo refinamientos **de código**. En tareas de prosa no se mueve aunque el Concilio reentre. |

## Seguridad

- No se lee ni vuelca `.env`.
- No se abre la DB de producción de Sentinel Omega desde el Concilio.
- Memory pack completo: solo con inject=true; orden `workspaces-dev` → `workspaces-test` → `workspaces`.
- `.concilio` = DATA (`<<<UNTRUSTED_DATA …>>>` / `<<<CONCILIO_DATA_NOT_INSTRUCTIONS>>>`).
- **Nunca se registra el token de Telegram.** `telegram_bot.py` redacta en el
  formateador de logging, no callando loggers: `httpx` lo escribía en la URL
  de cada petición, y `python-telegram-bot` lo incrusta en el mensaje de
  `InvalidToken`, que sale a nivel ERROR por encima de cualquier `setLevel`.
  El formateador es el último punto por el que pasan mensaje y traceback.

## Flujo

```
User task
  → RESEARCH (worker) → write .concilio → unload
  → CODING   (worker) → write .concilio → unload   [omitido en RESEARCH/QA]
  → REVIEW   (arbiter lee) + VERIFICADOR (ejecuta; manda sobre la lectura)
       no pasa → reentrada: el coder recibe PRIMERO los casos fallidos
       paran los frenos: entregable idéntico, o 4 rondas sin mejora > σ
  → SYNTHESIS (arbiter) → unload
```
