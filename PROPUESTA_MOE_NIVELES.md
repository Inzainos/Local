# Propuesta — Concilio MoE por niveles y por turnos

**Fecha:** 2026-09-24 · **Estado:** niveles definidos en `profiles/niveles.yaml`; motor de turnos pendiente

Todos los números vienen de medir la instalación real (`/api/show`, `/api/embed`),
no del manual.

---

## 0. El hallazgo que reordena las prioridades

El investigador no cabe en su propia ventana de contexto.

| Rol | Modelo | Ventana | Contexto inyectado hoy |
|---|---|---|---|
| **researcher** | `concilio-worker` (nemotron-mini) | **4.096** | ~4.831 tokens → **se pasa por 735** |
| coder | `concilio-medium` (deepseek-r1:8b) | 131.072 | le sobran 126.241 |
| optimizer | `concilio-arbitro` (gemma3:4b) | 131.072 | le sobran 126.241 |

La primera etapa —la que fija el marco para todo lo demás— trabaja con el
contexto truncado, **antes** de añadir siquiera el enunciado de la tarea. No es
que "se pierda en el contexto": es que no lo ve entero. Y los dos modelos con
ventana de 131k tienen 126.000 tokens ociosos.

La asignación está invertida. Cualquier cosa que construyamos encima arrastra
este defecto si no se corrige primero.

---

## 1. Inventario real (16 modelos)

Lo que discrimina no es el tamaño, es **ventana + herramientas**.

| Modelo | Tam | Ventana | Tools | Nota |
|---|---|---|---|---|
| `llama3.2:3b` | 2,0 G | **131k** | sí | mejor relación ventana/peso de toda la instalación |
| `nemotron-mini` (y `concilio-worker`/`lightest`) | 2,7 G | **4k** | sí | ventana diminuta — el cuello de botella actual |
| `gemma3:4b` (y `concilio-arbitro`/`heavy`) | 3,3 G | 131k | **no** | gran ventana pero sin herramientas |
| `mistral:7b` | 4,4 G | 32k | sí | |
| `qwen2.5-coder:7b` | 4,7 G | 32k | sí | especialista en código |
| `codegemma:7b` | 5,0 G | 8k | **no** | |
| `deepseek-r1:8b` (= `concilio-medium`) | 5,2 G | 131k | sí | razonador |
| `deepseek-r1:14b` | 9,0 G | 131k | sí | el más capaz disponible |
| `nomic-embed-text` | 0,27 G | 2k | no | embeddings, 768 dim |

**`gemma4:26b` ya no existe** — se borró tras confirmar OOM (18 GB, muere a los
159 s). No puede entrar en ningún nivel.

**Dos reglas que salen de la tabla:**

1. **Quien deba verificar contra archivos reales necesita `tools`.** Eso deja
   fuera a toda la familia gemma para investigación y código. Sirven, en cambio,
   para auditar y sintetizar, que es razonar sobre texto ya dado.
2. **Nemotron no debe ir primero.** Con 4k de ventana es el peor sitio para la
   etapa que más contexto recibe. Su lugar es una tarea acotada y corta.

---

## 2. Niveles

Tres escalones por tarea, y el Capitán decide en cuál entrar y cuándo escalar.

### Investigación

| Nivel | Modelos (en turnos) | Techo RAM | Cuándo |
|---|---|---|---|
| **Ligero** | `llama3.2:3b` → `nemotron-mini` | 2,7 G | por defecto |
| **Intermedio** | `llama3.2:3b` → `mistral:7b` → `gemma3:4b` (sintetiza) | 4,4 G | el ligero no llega al umbral |
| **Avanzado** | `llama3.2:3b` → `mistral:7b` → `deepseek-r1:8b` | 5,2 G | el intermedio tampoco |

### Código

| Nivel | Modelos (en turnos) | Techo RAM | Cuándo |
|---|---|---|---|
| **Ligero** | `llama3.2:3b` → `qwen2.5-coder:7b` | 4,7 G | por defecto |
| **Intermedio** | `qwen2.5-coder:7b` → `deepseek-r1:8b` | 5,2 G | el ligero no llega |
| **Avanzado** | `llama3.2:3b` → `qwen2.5-coder:7b` → `deepseek-r1:8b` | 5,2 G | el intermedio tampoco |

### Juez (audita al MoE que haya trabajado)

| Nivel | Modelo | Por qué |
|---|---|---|
| Normal | `gemma3:4b` | 131k de ventana, no necesita herramientas para auditar texto dado |
| Escalado | `deepseek-r1:8b` | cuando el juez normal no logra decidir en 2 rondas |

**El orden dentro de cada nivel es deliberado: del más débil al más fuerte.**
La deliberación secuencial sufre anclaje —el primero fija el marco y los
siguientes refinan dentro de él— así que el marco inicial debe ser tentativo y
el modelo capaz debe entrar con licencia para romperlo. Al revés, el mejor
modelo habla primero y los demás asienten.

**Techo de RAM por turnos:** el máximo es el modelo más grande del nivel, no la
suma. El ensemble actual corre concurrente y por eso pedía 5,7 G para tres
modelos chicos; en turnos el mismo trío pide 2,7 G.

**Corrección tras validar contra la máquina real.** La primera versión ponía
`deepseek-r1:14b` (9,0 G) en el nivel avanzado. No cabe: 7,9 G totales y ~5,5 G
disponibles con Sentinel corriendo — iría a swap. El avanzado usa
`deepseek-r1:8b` (5,2 G), el mayor que entra de verdad. El 14b queda en un
perfil `maximo` explícito que **exige detener Sentinel** y que el Capitán nunca
elige solo.

---

## 3. El turno

Cada modelo, en su turno:

1. Lee la **memoria del turno**: enunciado + borrador acumulado + qué objetó cada predecesor.
2. Decide: **`PASO`** (lo doy por bueno) o **`REFINO`** (y entrega su versión).
3. Cierra con una **puntuación 0-100** de su confianza en el resultado conjunto.

El nivel sube al Juez cuando **la media de las puntuaciones del turno alcanza el
umbral**. Si tras recorrer a todos los miembros no llega, el Capitán **escala al
siguiente nivel** con el borrador y las objeciones acumuladas.

El Juez aprueba o devuelve con retroalimentación al MoE de origen —investigación
o código— que reanuda turnos desde donde estaba.

### Lo que hay que cambiar en la memoria compartida

Hoy `data/moe_shared_memory.jsonl` guarda **el marcador, no el trabajo**:

```json
{"task":"...", "worker":"coder_qwen", "auditor":"audit_codegemma",
 "audit_score":90, "rounds":0}
```

Un modelo que entra en su turno necesita leer *el borrador del anterior*, y eso
no está. La entrada debe llevar `borrador`, `veredicto` (PASO/REFINO),
`objeciones` y `puntuacion` por turno.

---

## 4. La base vectorial — no es solo velocidad

Verificado: `nomic-embed-text` responde por `/api/embed` con vectores de **768
dimensiones**. Ollama los genera; no hace falta librería externa para eso.

Hoy se inyecta un pack **fijo** de 12.000 caracteres, venga o no a cuento de la
tarea. Por eso el investigador se desborda. Con búsqueda vectorial se inyecta
**solo lo pertinente**:

```
tarea → embedding → los k fragmentos más cercanos → contexto a medida
```

Eso convierte el problema de contexto en un problema de relevancia, y de paso
**deja de castigar a los modelos de ventana chica**: nemotron-mini con 1.500
tokens pertinentes rinde mejor que con 4.800 truncados a la fuerza.

**Ataca la alucinación en su raíz.** Un modelo inventa cuando le falta el dato
—como los 2 de 3 que se sacaron una ruta genérica el 16-sep—. Si el fragmento
correcto está en el contexto porque se recuperó por similitud, no hay hueco que
rellenar.

**Almacenamiento:** `sqlite3` (ya es stdlib) para los fragmentos y sus vectores,
y coseno en Python. Con el volumen que manejamos —unos pocos miles de
fragmentos— no hace falta FAISS ni Chroma. `numpy` no está instalado en este
venv y conviene añadirlo (dependencia pequeña, acelera el coseno).

---

## 5. Orden propuesto

1. **Arreglar la inversión de contexto.** Sacar a nemotron-mini de la primera
   etapa. Es un cambio de `config.yaml` y mejora hoy, sin esperar a nada.
2. **Memoria de turno.** Que guarde borrador + veredicto + objeciones. Sin esto
   los turnos no pueden encadenarse.
3. **Ensemble por turnos.** Quitar el `ThreadPoolExecutor` de
   `profile_pipeline.py` e iterar con `ensure_exclusive()`, que ya existe.
4. **Contrato de turno.** PASO/REFINO + puntuación, y el umbral del nivel.
5. **Escalado por niveles.** El Capitán elige nivel y escala; hoy solo clasifica
   investigación/código.
6. **Índice vectorial.** Indexar los documentos, recuperar por similitud y
   sustituir el pack fijo.

Los pasos 1 y 2 rinden de inmediato y no dependen del resto.

---

## 6. Lo que esto cuesta

Más lento por diseño. Un nivel de tres modelos en turnos son tres cargas de
Ollama —decenas de segundos cada una— más la inferencia. Escalar dos niveles
multiplica eso.

A cambio: cada modelo ve lo que hicieron los anteriores y puede contradecirlos,
que es justo lo que no ocurrió el 16-sep cuando dos modelos inventaron la misma
ruta y la fusión no lo detectó.

**Riesgo conocido:** el anclaje del primer turno. Mitigado con el orden
débil→fuerte, pero no eliminado. Conviene medirlo cuando esté en marcha —
comparar el veredicto del primer turno con el final y ver cuántas veces el MoE
cambia de opinión de verdad. Si casi nunca lo hace, los turnos están asintiendo,
no deliberando.
