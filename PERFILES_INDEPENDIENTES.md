# Perfiles independientes del Concilio — índice

Todo lo de este documento es **standalone**: no toca `config.yaml` ni el bot
de Telegram en producción (`consensus-telegram.service` / `consensus-web.service`).
Construido el 2026-09-16 en `/home/deamon/consensus-expert-agent`.

## Motores (`engine/`)

| Archivo | Qué hace |
|---|---|
| `readonly_tools.py` | 3 herramientas de solo lectura (`read_file`, `list_directory`, `grep_search`), sandboxed a `/home/deamon/consensus-expert-agent` y `/home/deamon/workspaces`. Probado contra path traversal y rutas fuera de lo permitido. |
| `tool_agent.py` | Bucle genérico de tool-calling sobre `/api/chat` de Ollama. Soporta `num_ctx` explícito (Ollama usa 2048 tokens por default sin importar el máximo del modelo — hay que pasarlo si el prompt puede ser grande). |
| `profile_pipeline.py` | Pipeline researcher→coder→optimizer con refinamiento (usado por `investigacion.yaml`/`general.yaml`). Incluye `_resolve_model`/`_tools_for_resolved_model`, reusados también por `moe_captain.py`. |
| `moe_captain.py` | Capitán + MoE: clasifica la tarea, elige un experto del work_pool, SIEMPRE audita con un modelo distinto del audit_pool, refina hasta el threshold. Soporta `persistent_memory_file` (memoria inyectada en workers/auditores, no en el capitán). |

## Perfiles (`profiles/`)

| Archivo | Patrón | Modelos | Estado |
|---|---|---|---|
| `investigacion.yaml` | researcher=ensemble concurrente (líder/lector/mapeador) + coder + optimizer | llama3.2:3b, nemotron-mini, qwen2.5:1.5b*, gemma3:4b, deepseek-r1:8b | Probado, funciona pero con calidad inconsistente en el líder/auditor (ver Limitaciones) |
| `general.yaml` | researcher/coder/optimizer secuenciales, sin ensemble | nemotron-mini, llama3.2:3b, gemma3:4b, deepseek-r1:8b | Construido, no tan probado como investigacion.yaml |
| `moe_captain.yaml` | Capitán (nemotron-mini) + work_pool/audit_pool genérico (code/investigacion/general) | Pensado para deepseek-r1:14b, qwen2.5-coder:7b, codegemma:7b, mistral:7b — hoy corre con fallbacks (ver abajo) | Probado end-to-end, funciona |
| `moe_sentinel.yaml` | Igual que moe_captain.yaml pero EXCLUSIVO a Sentinel Omega, con memoria persistente inyectada | Mismos pools que moe_captain.yaml | Probado — respuestas grounded correctas, PERO el rechazo de tareas fuera de alcance NO es confiable (ver Limitaciones) |

\* `qwen2.5:1.5b` fue borrado por el operador — el rol MAPEADOR de `investigacion.yaml` está roto hasta reasignarlo.

## CLIs

- `run_profile.py <perfil.yaml> <tarea> [--research-only] [--out archivo]`
- `run_moe.py <tarea>` (usa `profiles/moe_captain.yaml` fijo — no acepta perfil por ahora)

## Memoria (`data/`)

- `memory_packs/sentinel_omega_pack.md` — pack original (curado por otra sesión, "nemotron-super" según el operador). NO tocado.
- `memory_packs/sentinel_omega_moe_pack.md` — extiende el anterior con secciones 16-18: pipeline `infrastructure/pipeline/*.py` y `deploy/*.py` (docstrings verificados contra archivos reales el 2026-09-16), y nota de alcance exclusivo. Es lo que se inyecta en `moe_sentinel.yaml`.
- `moe_shared_memory.jsonl` / `moe_sentinel_memory.jsonl` — logs append-only de tareas corridas (no se inyectan automáticamente en el contexto todavía, solo se guardan).

## Modelos — estado de RAM/GPU (máquina: 7.8 GiB RAM, RTX 3050 Laptop 4GB VRAM vía Ollama en Windows host)

- `gemma4:26b` (18 GB) **NO cabe** — confirmado con prueba real (OOM tras 159s). Borrado.
- Modelos 1-5B (nemotron-mini, llama3.2:3b, qwen2.5:1.5b, gemma3:4b, deepseek-r1:8b): caben individualmente con margen; 3 concurrentes (~5.7GB) caben para el ensemble de `investigacion.yaml`.
- Modelos 7-14B pedidos (`deepseek-r1:14b`, `qwen2.5-coder:7b`, `codegemma:7b`, `mistral:7b`): **ya instalados** (2026-09-16, tras un primer intento cortado por falla de red). `_resolve_model` ya los usa como primarios automáticamente sobre los fallbacks. `deepseek-r1:14b` (9GB, razonador con cadenas de pensamiento largas) es lento con el pack inyectado — confirmado que NO truena la RAM, pero necesitó subir `worker_timeout_seconds` a 900 en `moe_sentinel.yaml` (el default de 180-420s no alcanzaba).
- Tool-calling nativo de Ollama: soportado por nemotron-mini, llama3.2:3b, qwen2.5:1.5b, deepseek-r1:8b. NO soportado por gemma3:4b (confirmado `/api/show` → capabilities).

## Limitaciones conocidas (no resueltas, no inventar que sí)

1. **Autoevaluación de score no es confiable por sí sola** — mitigado en `moe_captain.py` con auditor obligatorio de un modelo distinto (nunca el mismo que hizo el trabajo — ver validación `worker_cfg["model"] == auditor_cfg["model"]`).
2. **El líder/auditor del ensemble (`investigacion.yaml`) es inconsistente** — en 4 corridas de la misma tarea, la calidad varió de correcta a basura (llegó a descartar contenido real que sí leyó). Es un techo de capacidad de modelos 1-3B, no un bug de prompt.
3. **El rechazo de tareas "fuera de alcance" en `moe_sentinel.yaml` NO funciona de forma confiable** — probado con "¿capital de Francia?": el worker la contestó igual (con self-score 100) en vez de rechazarla. La instrucción de texto ("ALCANCE: rechaza esto") no vence al conocimiento general fuertemente arraigado del modelo.
   - **Próximo paso acordado**: reemplazar la inyección de texto plano por una DB vectorial (retrieval real) — si no hay contexto relevante recuperado para la tarea, esa ausencia de match es la señal de "fuera de alcance", en vez de depender de que el modelo se autocensure. Pendiente: `nomic-embed-text` ya está instalado (274 MB); falta construir el índice/chunking y la lógica de retrieval + threshold de similitud.
4. ~~La clasificación del capitán es poco confiable~~ **RESUELTO 2026-09-16**: nemotron-mini ignoraba la instrucción de texto "responde SOLO con la etiqueta" y contestaba la pregunta directamente (llegó a alucinar nombres de agentes inexistentes: "Event Horizon", "Sentinel", "Prevention"). Arreglado con decodificación restringida por JSON schema (`format` de Ollama) en vez de depender de que el modelo obedezca — confirmado con 3 preguntas distintas, siempre devuelve una etiqueta válida y ahora tarda <1s en vez de 20+. La calidad semántica del ruteo sigue siendo imperfecta ("escribe una función en python" clasificó como `general` en vez de `code`), pero ya nunca rompe el formato ni alucina.
5. **`num_ctx`/`timeout_seconds` no estaban seteados originalmente** — Ollama usaba 2048 tokens de contexto por default en TODAS las llamadas de esta sesión antes del fix (2026-09-16 ~08:30). Puede haber afectado pruebas anteriores a ese fix. Ya corregido en `tool_agent.py`/`moe_captain.py`, pero `profile_pipeline.py` (usado por `investigacion.yaml`/`general.yaml`) **todavía no tiene el fix** — pendiente si se retoma ese perfil.

## Config de producción (NO tocado salvo lo indicado)

- `config.yaml`: se agregaron cláusulas anti-alucinación a los 3 `system_prompt` (researcher/coder/optimizer) — esto SÍ es producción, ya está corriendo en vivo. Todo lo demás de este documento es aparte.
