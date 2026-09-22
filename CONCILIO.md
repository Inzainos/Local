# Sequential Concilio

## Qué es

Pipeline multi-agente **secuencial** sobre Ollama:

1. **Un solo modelo residente** a la vez (VRAM).
2. Ciclo por etapa: **load → run → write `data/sessions/<id>.concilio` → unload → next**.
3. Orden: **LIGHTEST → MEDIUM → HEAVY → LIGHTEST verify**.
4. Workers: `concilio-worker` (nemotron-mini) hace RESEARCH/REFINING y `concilio-medium` (DeepSeek R1) hace CODING.
5. Árbitro (`gemma3:4b` / `concilio-arbitro` / heavy) hace REVIEW + SYNTHESIS.
6. Umbral de consenso **85** (sin zona 80–84). Si &lt; 85 → reentrada completa (máx. 3 rondas).
7. El contenido de `.concilio` se inyecta **fenced como DATA**, nunca como instrucciones.
8. **`inject_sentinel_architecture: false`** por defecto — sin corpus de arquitectura Sentinel en cada run.
9. **Fast Gente/Estado** (`POST /api/ask`, `ConsensusOrchestrator.fast_ask`) queda **fuera** del Concilio.

Guía de agentes: [`AGENTS.md`](./AGENTS.md) (apunta a `/home/deamon/AGENTS.md`).

## Archivos clave

| Path | Rol |
|------|-----|
| `engine/orchestrator.py` | Orquestación secuencial + `fast_ask` |
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

Requiere bases: `gemma3:4b`, `nemotron-mini`.

## Config (`config.yaml`)

```yaml
consensus:
  threshold_score: 85
  max_refinement_rounds: 3
concilio:
  enabled: true
  sequential: true
  unload_between_stages: true
  arbiter_only_gemma: true
  inject_sentinel_architecture: false
  sessions_dir: data/sessions
  worker_model: concilio-worker    # LIGHTEST (nemotron-mini)
  coder_model: concilio-medium     # MEDIUM coder propio (DeepSeek R1); si falta cae al worker
  arbiter_model: concilio-arbitro  # HEAVY (gemma3:4b)
  fast_gente_outside: true
  verify_with_light: true
  hard_rules_stub: data/memory_packs/home_hard_rules_stub.md
context_injector:
  enabled: false
```

Si `concilio-*` no está en `ollama list`, el orquestador cae a `nemotron-mini` / `gemma3:4b`.
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

**Criterio de archivo: solo se recuerda lo que superó el umbral.** Una
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
  → REVIEW   (arbiter) → score ≥85?
       no → reentrada completa (hasta max rounds) + LIGHT verify
  → SYNTHESIS (arbiter) → unload
```
