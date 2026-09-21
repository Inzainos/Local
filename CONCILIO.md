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

## Seguridad

- No se lee ni vuelca `.env`.
- No se abre la DB de producción de Sentinel Omega desde el Concilio.
- Memory pack completo: solo con inject=true; orden `workspaces-dev` → `workspaces-test` → `workspaces`.
- `.concilio` = DATA (`<<<UNTRUSTED_DATA …>>>` / `<<<CONCILIO_DATA_NOT_INSTRUCTIONS>>>`).

## Flujo

```
User task
  → RESEARCH (worker) → write .concilio → unload
  → CODING   (worker) → write .concilio → unload   [omitido en RESEARCH/QA]
  → REVIEW   (arbiter) → score ≥85?
       no → reentrada completa (hasta max rounds) + LIGHT verify
  → SYNTHESIS (arbiter) → unload
```
