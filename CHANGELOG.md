## [3.0.3] - 2026-10-01 — un aviso de la cola ya no se pierde en silencio

El mismo hueco que cerró la 3.0.2 para las tareas del concilio seguía abierto, idéntico, en la
cola de alertas: `pop_batch()` borraba el aviso del archivo **antes** de enviarlo, así que entre
ese borrado y el `send_message` el aviso sólo existía en memoria del proceso. Un corte ahí —y aquí
los reinicios de Windows cortan procesos a mitad, pasó el 25-sep 13:16— se llevaba hasta 5 avisos
del Sentinel sin dejar rastro ni en un archivo ni en el log. No hubo incidente que lo delatara:
salió revisando el código del poller.

- **En vuelo** (`alert_queue.py`): lo que sale de la cola queda en `data/alert_queue_inflight.json`
  hasta que se confirma. `recover_inflight()` lo devuelve a la **cabeza** de la cola al arrancar,
  con un WARNING que dice cuántos eran. Asume un solo consumidor, que es lo que garantiza systemd.
- **Tope de 5 reintentos**: un aviso que Telegram rechaza siempre (HTML inválido, mensaje largo, un
  chat que bloqueó al bot) se reinsertaba al **frente** cada 5 s para siempre, y la cola es FIFO:
  tapaba indefinidamente todo lo que venía detrás. Al agotarlos pasa a `alert_queue_dead.json` —se
  guarda, no se borra— y `descartados` sale en `/queue`, en la Mini App y en `/api/alerts/stats`.
  Un fallo que no es del aviso (sin `TELEGRAM_CHAT_ID`) no gasta intentos: si no, una configuración
  a medias descartaría la cola entera en cinco vueltas.
- **Entrega parcial** (`telegram_bot.py`): bastaba que **un** chat aceptara para marcar el aviso
  entregado y destruirlo; los demás se quedaban sin él y nadie lo sabía. El reintento va ahora sólo
  a los chats que faltan, sin duplicárselo a quien ya lo recibió.
- **Compatible en los dos sentidos** mientras no se reinicien los servicios: el bot vivo tiene el
  módulo viejo en memoria y el Sentinel importa `alert_queue.py` por ruta absoluta desde sus propios
  procesos, así que un aviso recién encolado se sigue escribiendo con el esquema de antes (`_a_dict`
  omite los campos nuevos cuando no dicen nada) y la hidratación ignora las claves que no conoce.
- 13 tests nuevos (240 → 253, cero saltados); los 4 arreglos sobreviven a mutación, cada uno lo
  detecta su prueba. Sin desplegar: los servicios cargan el código al arrancar.

## [3.0.2] - 2026-09-25 — una tarea interrumpida ya no se pierde en silencio

El 25-sep a las 13:16 un reinicio de Windows cortó una tarea del concilio a los 10 minutos,
con el código ya correcto en la pizarra (16/16 al re-verificarlo). No se entregó nada y el
operador se quedó esperando una respuesta que nunca iba a llegar.

- `memory/concilio_store.py`: esquema 2 con `cerrado`. `cerrar()` lo marca; `sesiones_interrumpidas()`
  devuelve las que empezaron y nunca se cerraron. Las sesiones del esquema 1 se **ignoran**: se
  escribieron sin el campo y darlas por cortadas sería inventar.
- `engine/orchestrator.py`: el cuerpo pasa a `_run_consensus` y `run_consensus` lo envuelve en un
  `finally` que cierra la sesión — salida normal, vía directa y excepción. La lista de sesiones
  abiertas es local a la llamada, no un atributo: dos tareas a la vez no se pisan.
- `telegram_bot.py`: al arrancar avisa de lo que quedó a medias, en texto plano (el enunciado es
  del operador y puede traer `*` o backticks). Sólo cierra lo que **se pudo enviar**: si Telegram
  no responde o no hay `TELEGRAM_CHAT_ID`, el aviso queda para el próximo arranque.
- 16 tests nuevos; las 5 piezas nuevas sobreviven a mutación. Probado contra una copia de la
  sesión real que se cortó.

## [3.0.1] - 2026-09-25 — el verificador rechazaba código correcto por otra redacción

Primera tarea real tras desplegar la v1, por Telegram: «validar_token_telegram … que acepte
identificador numerico, DOS PUNTOS y un secreto de EXACTAMENTE 35…». El código del concilio era
correcto (`^[0-9]+:[A-Za-z0-9_-]{35}$`) y se entregó «SIN CONSENSO 15/16» porque un caso
construido estaba mal: `'18:<35 válidos>'` → `False`.

- **Causa**: el extractor dio al identificador longitud máxima 1 y la defensa «el número tiene
  que aparecer en el texto» lo aceptó porque «**un** secreto» contaba como 1. La excepción del 1
  era para el mínimo implícito y cubría también el máximo.
- **Arreglo** (`engine/especificacion.py`): «un/una» ya no cuentan como 1 (artículos); el «dos»
  de «dos puntos» ya no cuenta como 2 (se quitan los separadores nombrados antes de contar,
  también le llega a `segmentacion.py`); el 1 sólo está exento como mínimo; un número dicho una
  vez sólo puede medir un campo; y el extractor tiene **un reintento** con el motivo del rechazo,
  que pasa por las mismas defensas.
- **Bucle del extractor**: con es_palindromo y a_romano, qwen decía `aplica: false` y se quedaba
  en bucle dentro de `funcion` hasta los 180 s. Topes `maxLength`/`maxItems` en el esquema (5-6 s)
  y tiempo de espera del extractor 90 s.
- Medido con `bench/extractor_redacciones.py`: 10/10, cero rechazos falsos, cero aprobaciones
  falsas. 10 tests nuevos; las 5 defensas nuevas sobreviven a mutación (cada una la detecta un test).

## [3.0.0] - 2026-09-25 — v1.0-estable: los modelos comprueban su trabajo ejecutándolo

Primera versión estable de la arquitectura de verificación. 50 commits en dos días, casi todos
con una medición detrás. La idea central: **un modelo no decide si su código funciona
leyéndolo**. Medido: el árbitro leyendo puso 92, 93 y 96 a tres códigos que rechazaban todos los
tokens válidos (acierto real 78 %, 38 %, 78 %), y 97–99 a otro que ni compilaba.

### La v1 en una línea
Tarea de código → el coder escribe la función en **una** llamada → el **verificador la ejecuta**
contra casos construidos desde el enunciado → se entrega **verificada**, o **rotulada SIN
VERIFICAR** si el enunciado no admite casos fiables, y sólo si falla con casos fiables entra el
concilio.

### Aceptación
Siete tareas con verdad escrita a mano, por `run_consensus` real (`bench/aceptacion.py`). Criterio
de «estable»: **cero consensos falsos** (nada verificado que la vara independiente no confirme).

| pasada | tareas | tiempo | consensos falsos |
|---|---|---|---|
| 1.ª (antes de «todos o ninguno») | 7 | 12,4 min | **1**: `es_matricula` aprobada con 15/16 por el umbral de 85 (aceptaba `'!OV-3074'`) |
| **2.ª** | 7 | 26,0 min | **0** |
| comprobación del mejor intento | `es_matricula` | 16,4 min | **0** |

En la 2.ª pasada: `validar_token` **verificada 16/16 en 1,1 min** (el 24, por el concilio: 44,8 min
sin cerrar); cinco tareas sin verificar —no admiten casos fiables— y **las cinco correctas** según
la vara; `es_matricula` escaló al concilio y no cerró. El concilio empeoró su código (15/16 → 8/16,
y en la comprobación → 0/16); con el mejor intento se entrega el 15/16 con el caso que falla.

### Added
- **Verificador por ejecución** (`engine/verificador.py`): casos derivados del ENUNCIADO, nunca
  de la solución; ejecución en proceso aparte con límite de tiempo y memoria y sin red.
- **Especificación de formato** (`engine/especificacion.py`): un modelo extrae campos, longitudes
  y separadores con decodificación restringida; Python construye casos balanceados de frontera.
  Ninguno de 5 modelos locales construyó un solo caso válido para «EXACTAMENTE 35 caracteres»;
  `len()` sí. Defensas medidas: números que el enunciado no dice, separadores que no nombra,
  funciones que no devuelven `bool`.
- **Vía directa** en `run_consensus`: una llamada + verificar; 2.º intento con los casos fallidos;
  concilio sólo si falla. Bot, CLI y web muestran sus desenlaces sin decir nada falso.
- **Frenos de estancamiento**: entregable idéntico dos rondas, o 4 rondas sin mejorar por encima
  del ruido medido (σ 6,9).
- **Filtro de relevancia de la memoria** (idf) para antecedentes y hechos.
- **Mejor intento medido**: si nadie cierra, se entrega el candidato con más casos acertados de
  todos los medidos (vía directa y rondas del concilio), rotulado con lo que falla.
- **`ESTADO.md`** (set point para retomar si se corta una sesión) y **`bench/`** (los arneses que
  decidieron cada elección, con sus resultados).
- Motor de turnos, adaptador y capitán por niveles (`engine/turnos*.py`): escritos y probados,
  no cableados (v2). Segmentador (`engine/segmentacion.py`): escrito, desactivado por medición.

### Changed
- **Coder: `codegemma:7b`** (7 tareas, 72/73 casos a la primera; qwen 60/73; deepseek-r1:8b se
  gastó 15 min pensando sin escribir la función). Extractor de formato: `qwen2.5-coder:7b`.
- **nemotron-mini sólo como portero**; capitán `llama3.2:3b`.
- **Caché KV de Ollama en `q8_0` + flash attention**: 7,28 → 6,21 GiB, +13 % de generación.
- Con casos de especificación se exigen **todos**; los derivados por un modelo **no aprueban**.
- `profiles/niveles.yaml` redimensionado con la máquina correcta (host 11,71 GiB medido en
  Windows, no con `free` de WSL) y con caché `q8_0`.
- Tuberías viejas (`run_moe`, `run_profile`) retiradas a `legacy/` con `git mv`.

### Fixed (los que cambiaban resultados)
- `num_ctx` no llegaba a la precarga: Ollama reservaba 25,7 GB para prompts de 5.000 tokens.
- El score de LECTURA cerraba rondas cuando el verificador no podía ejecutar.
- Conjuntos de casos con 7 de 8 iguales daban 88 % a código que rechazaba todo.
- El verificador ejecutaba prosa y bloques de código pegados: cuatro «no compila» falsos.
- El coder recibía el elogio de 99 primero y el fallo al final, en un bloque que se le manda
  ignorar.
- La memoria inyectaba las 5 tareas más recientes sin filtro, y archivaba como «aprobado» código
  roto: 8 hechos en `knowledge_facts_cuarentena`, ninguno borrado.
- `run_with_tools` no enviaba temperatura: el `0.0` del capitán nunca llegó a Ollama.
- El freno comparaba con `>` estricto contra una señal con σ 6,9.
- El guardián de pyflakes pasaba en vacío si la herramienta no estaba instalada.
- Seis «hermanos» de arreglos que se habían quedado con la versión vieja (barrido completo).
- `scripts/create_concilio_models.sh` no creaba `concilio-investigador`, el investigador de la v1.

### Despliegue
Los servicios `consensus-telegram` y `consensus-web` **cargan el código al arrancar**: hasta
`sudo systemctl restart consensus-telegram consensus-web` siguen con la versión anterior.

## [2.4.0] - 2026-09-21 — Memoria del Concilio, y tres fugas de token

### Added
- **El Concilio recuerda entre sesiones.** `blackboard_snapshots` acumulaba tareas resueltas desde siempre (108 en la base al momento del cambio) pero su único lector, `get_recent_tasks()`, no tenía llamadores. Tampoco los tenían `save_fact()`, `search_facts()` ni `get_conversation_history()`: se escribía memoria y no se leía ninguna. Ahora:
  - `SharedMemory.recuperar_tareas_previas()` — antecedentes de deliberaciones anteriores (enunciado + veredicto), excluyendo la tarea en curso.
  - `SharedMemory.recordar_consenso()` — archiva enunciado + síntesis en `knowledge_facts` **solo si el score alcanza el umbral**. Criterio del operador: se recuerda lo que el Concilio aprobó; un borrador reprobado no entra a la memoria.
  - `SharedMemory.buscar_hechos()` — recupera hechos por las palabras de 5+ letras del enunciado (`search_facts` hace `LIKE`; el enunciado completo casi nunca casa).
  - `ConsensusOrchestrator._bloque_memoria_historica()` inyecta ambos en `research_context`, que ya leían Researcher, Coder y Optimizer.
- Todo el bloque va cercado con `fence_untrusted(role="historial_tareas")`: las síntesis pasadas son salida de modelo, no entrada del operador. Verificado con hechos envenenados — la orden queda marcada como intento y un `<<<END_UNTRUSTED_DATA>>>` falsificado se degrada a literal.
- `Blackboard.concilio_rounds` — rondas completas `light→medium→heavy→verify`, que sella el orquestador. `refinement_rounds` solo subía con artefactos de **código** (`blackboard.py`: `if is_refinement and self.code_proposal`), así que en tareas de prosa el contador no se movía aunque el Concilio reentrara: 31 de 40 tareas sin consenso figuraban con 0 rondas.
- `Blackboard.consensus_threshold` — la barra contra la que se juzgó **esa** tarea. Los snapshots anteriores al campo dicen "no registrado" en vez de un número inventado.

### Fixed
- **Tres fugas del token de Telegram, en capas distintas.** Medido en el servicio vivo: 75.678 líneas del journal con tokens en claro, y no uno sino dos (el revocado y su reemplazo).
  1. `logging.basicConfig(level=INFO)` ponía el root logger en INFO y `httpx` registraba la URL completa de cada petición — contra la API de Telegram esa URL lleva el token. Un sondeo cada 10 s.
  2. `python-telegram-bot` incrusta el token **en el mensaje** de `InvalidToken`; al propagar, el traceback lo escribía en stderr, y con `Restart=` lo reimprimía en cada reintento.
  3. Callar loggers no bastaba: PTB registra ese traceback a nivel ERROR, por encima de cualquier `setLevel(WARNING)`. Se redacta en el **formateador**, último punto por el que pasan mensaje y traceback. El regex va sin `\b` inicial a propósito: en la URL el token viene pegado al prefijo `bot`, donde no hay frontera de palabra.
  Verificado contra los tres tokens reales del incidente, por ambas vías: 6/6 redactados, `bot_id` conservado para poder diagnosticar.
- **El veredicto ahora dice lo que pasó.** El encabezado rezaba "Consenso Final" también sin consenso, con el aviso degradado a viñeta de segunda línea: una respuesta de 73 llegaba bajo un título que afirmaba lo contrario. El CLI decía "Límite Rondas", que sonaba a incidencia de proceso.
- **MAPEADOR reasignado** a `nemotron-mini`. `profiles/investigacion.yaml` apuntaba a `qwen2.5:1.5b`, desinstalado, y era el único `model:` del archivo sin `fallback_model`. Se descartó `llama3.2:3b` pese a ser más pequeño: es el modelo del LÍDER, y el LÍDER audita al MAPEADOR — mismos pesos es la peor posición para detectar una ruta inventada, que es el bug del 2026-09-16 que el ensemble existe para evitar. Capacidades verificadas con `/api/show`, no con la documentación.

### Removed
- 476 líneas de tres implementaciones paralelas muertas: `engine/concilio_session.py`, `memory/concilio_session.py`, `memory/session_store.py`, `engine/ollama_lifecycle.py`. El store vivo es `ConcilioStore`; el gestor de modelos vivo es `ModelLifecycle`. Lo que justificaba borrarlas: las dos clases `ConcilioSession` compartían **nombre** y no compartían una sola función.

### Notes
- El umbral de 85 **no se tocó**. El 37 % de tareas sin consenso no es un defecto: los enunciados que fallan son de una o dos palabras (`status`, `revisa sistema`, `entrenamiento`, 55-78 puntos). El umbral rechaza deliberaciones sobre peticiones mal especificadas, que es su trabajo.
- Pendiente del operador: purgar el journal histórico y rotar el token, que estuvo expuesto en disco.
- Sin efecto hasta la próxima deliberación real; `knowledge_facts` sigue en 0 filas por diseño (solo se llena con consensos nuevos).

## [2.3.1] - 2026-09-15 — Coder MEDIUM propio: DeepSeek R1

### Changed
- El rol **coder (MEDIUM)** ya no comparte binario con el researcher: usa modelo propio **`concilio-medium` → `deepseek-r1:8b`** (razonador). Researcher sigue en `concilio-worker` (nemotron-mini), árbitro en `concilio-arbitro` (gemma3:4b).
- `config.yaml`: nuevo `concilio.coder_model: concilio-medium`; `roles.coder` → model `concilio-medium`, fallback `deepseek-r1:8b`, `max_tokens` 800→1600 (espacio para el razonamiento).
- `engine/orchestrator.py`: resuelve el modelo del coder por separado (candidatos `concilio-medium`/`deepseek-r1:8b`), ya no fuerza `coder = worker`; `concilio-medium` sacado de los candidatos del worker para que el researcher nunca cargue el pesado.
- `modelfiles/Modelfile.medium`: `FROM deepseek-r1:8b`, recreado.

### Notes
- Secuencial (un modelo a la vez): DeepSeek 5.2GB carga solo en la etapa de código; verificado en 5.6GB con swap negligible (~20KB). Si falla, cae al worker ligero.

## [2.3.0] - 2026-09-14 — Migración de modelos (gemma4 → gemma3:4b / nemotron-mini)

### Changed
- **Bases del Concilio actualizadas** tras eliminar `gemma4:26b` (17 GB, no cabía en 5.6 GiB de RAM):
  - HEAVY / Árbitro: `gemma4:26b` → **`gemma3:4b`** (3.3 GB).
  - Worker LIGHTEST + MEDIUM: `qwen2.5:1.5b` → **`nemotron-mini`** (2.7 GB).
- Modelfiles (`Modelfile.concilio-*`, `Modelfile.arbitro|heavy|worker|medium|lightest`, `Modelfile.sentinel-concilio-*`) apuntan a las nuevas bases.
- `config.yaml`: `fallback_model` researcher/coder → `nemotron-mini` (corrige typo `nemotron:mini`), optimizer → `gemma3:4b`.
- `engine/orchestrator.py`: defaults y candidatos hardcodeados `gemma4:26b` → `gemma3:4b`; guardas de "no usar árbitro como worker" ahora sobre `gemma3`.
- `engine/model_lifecycle.py`, `cli.py`, `scripts/create_concilio_models.sh`, `README.md`, `AGENTS.md`, `CONCILIO.md`, `docs/CONCILIO.md`, `modelfiles/README.md` alineados a las nuevas bases.
- Modelos custom recreados: `ollama create` de `concilio-worker` (nemotron-mini) y `concilio-arbitro` (gemma3:4b) + aliases sentinel.

### Notes
- Pipeline secuencial (un modelo a la vez, unload entre etapas): con árbitro 3.3 GB y worker 2.7 GB cabe holgado en 5.6 GiB sin swap agresivo.
- `docs/HANDOFF_GEMMA_MEMORIA.md` queda como referencia histórica del árbitro Gemma anterior.

## [docs] - 2026-09-13 — Auditoría GitHub (Claude/Copilot)

### Notes
- Auditoría 13-sep en `Inzainos/Local` rama `local/concilio`: **limpio / cero secretos**.
- `.env`, `.env.tmp`, `*.bak*`, quarantine fuera de git (`.gitignore`).
- Sin remediación pendiente en esta rama.

## [2.2.6] - 2026-09-13 — Mini App HTTPS (cloudflared-mini)

### Added
- User-unit `cloudflared-mini.service` + `scripts/run_cloudflared_mini.sh`: quick tunnel a `:8002`, publica URL trycloudflare, actualiza `TELEGRAM_WEBAPP_URL=.../mini` y reinicia el bot.
- `Linger=yes` para usuario `deamon` (tunel sobrevive sin sesion interactiva).

### Changed
- `CONSENSUS_DASHBOARD_URL` default/.env -> `http://127.0.0.1:8002`.

### Notes
- URL trycloudflare es **efimera** (cambia al reiniciar el tunel). Tunel nombrado/ngrok = escalacion futura.
- Builds on **2.2.5** (light/heavy cut).

## [2.2.5] - 2026-09-13 — Telegram light/heavy cut + audit Sentinel

### Changed
- `/task` ahora es vía **ligera**: `orchestrator.fast_ask(..., preload_sentinel=True)` (pack `data/memory_packs/sentinel_omega_pack.md`, tope ~8k).
- `/concilio` queda para el **Concilio completo** (light→medium→heavy→verify, umbral 85).
- Preguntas de eventos/precursores/muro/alertas en `/task` leen la **DB Sentinel** (`sentinel_proximos_eventos`), no alucinan TV.
- `/help` y menú alineados: `/task` ligero · `/concilio` heavy.
- `audit_project(..., with_sentinel=True)` inyecta pack/pipeline Sentinel **solo** durante `/audit`; restaura `inject_sentinel_architecture` al valor previo (default config sigue `false` para runs normales).

### Fixed
- Auth de `/concilio` usa `is_authorized` (no `_ensure_auth` inexistente).

### Ops
- Units `consensus-telegram.service` y `consensus-web.service` (:8002) documentados como deploy activo (`enabled`/`active` en host).
- Ollama API en `:11434` via **Windows** `ollama.exe` (unit Kali `ollama.service` se deja disabled para evitar choque de puerto).

### Notes
- Dashboard web `:8002` sigue en Concilio completo / fast paths de UI.
- Mini App local: `http://127.0.0.1:8002/mini` (botón Telegram necesita `TELEGRAM_WEBAPP_URL` HTTPS).
- No se tocó `.env` ni DB prod ni systemd de Sentinel en este doc bump.

## [2.2.4] - 2026-09-11 — Concilio reliability (full re-entry / score / session)

### Fixed
- **Full re-entry** when verified score < 85: loop is lightest → medium → heavy → lightest verify (not coder-only refine). Respects `max_refinement_rounds` and `auto_refine`.
- **Unload always runs**: `_run_exclusive` unloads in `finally` even if stage callbacks throw.
- **Score parse robustness**: verifier accepts `[PUNTUACION_VERIFICADA|CONSENSO]` and `score: N`; no longer grabs arbitrary first digits.
- **Session write durability**: `.concilio` save uses tmp + `fsync` + `os.replace` (+ dir fsync best-effort).
- **Quarantine** leftover `engine/orchestrator.py.broken`.

### Changed
- `health().concilio.order` documents full re-entry path.

### Notes
- Does not touch `.env`, Sentinel prod DB, or systemd units.
- Telegram bot / Mini App paths untouched.

# Changelog

## [2.2.3] - 2026-09-10 — Prod deploy units

### Added
- `deploy/consensus-telegram.service` y `deploy/consensus-web.service` (Mini App en **:8002**; :8000 ocupado).
- Bot Telegram ya en ejecución bajo usuario `deamon`; web Mini App en `http://127.0.0.1:8002/mini`.

### Notes
- Instalar units requiere sudo (ver docs/FUNCIONAMIENTO_TELEGRAM.md).
- Sentinel `sentinel-omega.service` ya estaba **active** en este host.


## [2.2.2] - 2026-09-10 — Telegram status/reporte + Mini App

### Added
- `/status` enriquecido y nuevo `/reporte`: Concilio health (umbral 85, sequential, model tags, sesiones `.concilio`, `alert_queue.get_stats`) + Sentinel read-only; sin secretos.
- Mini App `static/mini.html` servida en `/mini` y `/static/`; API `/api/mini/status` (+ `/mini` / `/static/mini.html`).
- `TELEGRAM_WEBAPP_URL` en `.env.example`; botón WebApp en `/start` cuando la URL está configurada.
- Link README → `docs/HANDOFF_GEMMA_MEMORIA.md`.

### Changed
- `TELEGRAM_BOT_README.md` documenta Mini App, `/status` y `/reporte`.
- Politica alertas: digest horario siempre; inmediato solo sin precedentes; bot = `/task` + reportes + cola.

### Notes
- Leftover: HTTPS publico para `TELEGRAM_WEBAPP_URL` (Telegram Mini App).
- No se reescribio el orchestrator; no se toco Sentinel prod; no se volco `.env`.

---

## [2.2.1] - 2026-09-03 — Docs/config thin + home hard-rules sync

### Added
- `AGENTS.md` local (apunta a `/home/deamon/AGENTS.md` + reglas Concilio).
- Stub opcional `data/memory_packs/home_hard_rules_stub.md` (mapa home + reglas duras; **no** auto-inject).
- Comentarios de hard rules / project map al inicio de `config.yaml`.
- `concilio.inject_sentinel_architecture: false` y `context_injector.enabled: false` explícitos.
- `concilio.hard_rules_stub` path documentado.

### Changed
- Roles renombrados a Worker-Research / Worker-Coder / Arbitro (ya no Nemotron/DeepSeek como identidad).
- Modelos preferidos: `concilio-worker` / `concilio-arbitro` (fallbacks `qwen2.5:1.5b` / `gemma4:26b`).
- System prompts thin con reglas home inline (secretos/env, cero sintéticos, forward-only, no prod DB) sin exigir corpus Sentinel.
- `ResearcherAgent` ya **no** auto-carga `load_repository_context()` cuando inject=false.
- Preferencia de tags Ollama: con inject=false prioriza `concilio-*` antes que `sentinel-concilio-*`.
- README / CONCILIO.md / docs/CONCILIO.md alineados a la realidad actual.

### Policy
- Sin inyección Sentinel por defecto hasta que terminen updates Sentinel en otro hilo.
- Builds on Concilio **2.2.0** + audit **2.1.1**.

---

## [2.2.0] - 2026-09-03 — Concilio thin (no Sentinel injection)

### Added / Fixed
- Full Concilio order: LIGHTEST -> MEDIUM -> HEAVY -> LIGHTEST verify.
- Between stages: write data/sessions/<id>.concilio + unload (never two models).
- If score < 85: full re-entry (not coder-only refine) until threshold or max_refinement_rounds.
- .concilio / UNTRUSTED_DATA fenced as DATA (memory/anti_injection.py + ConcilioStore).
- Thin Modelfiles (modelfiles/Modelfile.lightest|medium|heavy); scripts/create_concilio_models.sh.
- config: concilio.inject_sentinel_architecture: false; context_injector.enabled: false.
- researcher no longer auto-loads Sentinel repository_context.
- main.py --check reports tiers and unloads models.

### Policy
- Do NOT use Modelfile.sentinel-concilio-* for default Concilio.
- Builds on audit v2.1.1.


## [Unreleased] — 2026-09-03 — Sequential Concilio + Sentinel Modelfiles

### Added
- **Sequential Concilio**: one agent at a time; write `data/sessions/<id>.concilio`; `ollama stop`/unload before next role so `gemma4:26b` / `sentinel-concilio-arbitro` can run as final arbiter without sharing RAM.
- **`.concilio` store** (`memory/concilio_store.py`): JSON sections task/research/code/critique/scores/round; Concilio-roles-only; not web-UI executable.
- **Anti-injection** (`memory/anti_injection.py`): fence/strip untrusted blackboard & user content; preamble DATA_NOT_INSTRUCTIONS.
- **Memory pack** `data/memory_packs/sentinel_omega_pack.md` (+ `scripts/build_memory_pack.py` from DEV docs; no `.env` secrets).
- **Modelfiles**: `sentinel-concilio-arbitro` (FROM gemma4:26b), `sentinel-concilio-worker` (FROM qwen2.5:1.5b) + `scripts/create_concilio_models.sh`.
- **CONCILIO.md** short ops guide. Documents dashboard `POST /api/ask` (Estado; no "Gente" tab) as OUTSIDE Concilio.

### Changed
- `config.yaml`: researcher/coder → `sentinel-concilio-worker` (fallback `qwen2.5:1.5b`); optimizer → `sentinel-concilio-arbitro` (fallback qwen). Threshold single **85**.
- `engine/orchestrator.py`: exclusive model lifecycle per role; sync `.concilio` after each stage.
- `memory/blackboard.py` + `agents/researcher.py`: fenced prompts.

### Policy
- Never keep 26b + another chat model loaded together.
- Do not touch Sentinel prod DB / systemd from this agent.


# Changelog - Consensus Expert Agent / Concilio

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-09-03

### Added — Standalone Concilio pipeline (chain/rhythms)
- **Sequential unload**: un modelo Ollama en VRAM a la vez (`keep_alive: 0` + `unload()` entre roles).
- **Session files**: `data/sessions/<id>.concilio` tras cada etapa (INIT/RESEARCH/CODING/REVIEW/REFINE/SYNTHESIS).
- **DATA fencing**: `<<<CONCILIO_DATA_NOT_INSTRUCTIONS>>>` … `<<<END_CONCILIO_DATA>>>` al reinyectar sesión/pizarra.
- **Thin Modelfiles** opcionales: `modelfiles/Modelfile.worker` (FROM qwen2.5:1.5b), `modelfiles/Modelfile.arbitro` (FROM gemma4:26b) — SYSTEM solo anti-inyección + formato de score.
- **CONCILIO.md**: descripción breve de la cadena/rhythms (sin arquitectura Sentinel).
- **`pipeline` + `context_injector.enabled: false`**: modo standalone por defecto.

### Changed
- System prompts de roles: sin corpus Sentinel; umbral único **85** (sin gap 80–84).
- Nombres de rol: Worker-Research / Worker-Coder / Arbitro-Gemma; `preferred_model` concilio-* si existe.
- Researcher/Coder/Optimizer dejan de exigir reglas Sentinel en prompts de usuario.
- README alineado al pipeline standalone.

### Notes
- Integración Sentinel diferida (otro agente). No se tocó DB de producción ni se volcaron secretos `.env`.

## [2.1.1] - 2026-09-03

### Fixed — Audit Kali WSL
- **Optimizer prompt gap**: system prompt decía aprobar ≥85 pero exigir cambios solo si <80 (80–84 indefinido). Ahora un solo umbral alineado a `consensus.threshold_score` (85).
- **`alert_queue.get_stats()`**: `/queue` del bot llamaba un método inexistente → AttributeError. Implementado con contadores persistentes, `requeue`, `mark_sent`/`mark_failed` y escritura atómica.
- **Alert poller**: si el envío a Telegram falla, la alerta se reencola (antes se perdía tras `pop_batch`).
- **`timeout_retries`**: estaba en `config.yaml` pero no se usaba; ahora reintenta timeouts/transporte en `BaseExpertAgent.generate`.
- **SQLite path**: `data/shared_memory.db` relativo se resuelve contra el directorio del `config.yaml` (no contra el CWD).
- **Context injector**: orden de `workspace_roots` pasa a preferir `workspaces-dev` → `workspaces-test` → `workspaces` (prod al final).
- **Telegram auth**: callbacks inline ahora pasan por `is_authorized`; chat IDs separados por coma se comparan con `.strip()`.
- **`run_telegram_bot.sh`**: carga `.env` correctamente.
- **Score parse**: fallbacks del optimizador usan el threshold configurado.
- **Pipeline routing**: RESEARCH/QA omiten fase de código y refinamiento inútil.
- **README**: alineado a modelos instalados (`qwen2.5:1.5b`, `gemma4:26b`).
- **deps**: `python-dotenv` añadido a `requirements.txt`.

### Notes
- Roles Nemotron/DeepSeek/Gemma como nombres; researcher/coder compartían binario hasta especialización.
- No se tocó la DB de producción de Sentinel Omega.

## [2.1.0] - 2026-09-01

### Added - Telegram Bot Integration
- Bidirectional Telegram integration (Consensus ↔ Sentinel alerts)
- Bot commands: `/task`, `/audit`, `/status`, `/blackboard`, `/cancel`
- See TELEGRAM_BOT_README.md

## [2.0.0] - 2026-08-XX

### Added - Core Consensus System
- Multi-model consensus engine via Ollama
- Shared memory blackboard (SQLite)
- Iterative refinement with consensus scoring (0-100)
- Web dashboard + CLI

## [1.0.0] - 2026-08-XX

### Added - Initial Release
- Basic consensus orchestrator, memory, configuration
