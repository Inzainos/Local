# bench/ — las mediciones que decidieron la v1

Cada decisión de la v1 se tomó midiendo. Estos son los arneses, para poder **repetir** cada
medición en vez de fiarse de lo que dice un documento. Se ejecutan con el intérprete del
entorno y **necesitan Ollama libre** (cargan modelos reales):

```bash
cd /home/deamon/consensus-expert-agent
.venv/bin/python bench/aceptacion.py        # la definición de «estable»
```

`tareas_ref.py` contiene sólo datos (siete tareas con verdad escrita a mano); importarlo no
ejecuta nada. Los demás scripts **sí se ejecutan al importarse**: no los importes, córrelos.

| arnés | qué mide | resultado (2026-09-25) | decisión que tomó |
|---|---|---|---|
| `aceptacion.py` | las 7 tareas por `run_consensus` real, juzgadas con verdad escrita a mano | ver `CHANGELOG.md` → Aceptación | la v1 es estable si hay **cero consensos falsos** |
| `comparar_coders.py` | codegemma vs qwen, una llamada, temperatura 0 | codegemma 6/7 tareas, 72/73 casos; qwen 5/7, 60/73 | coder = `codegemma:7b` |
| `comparar_derivadores.py` | 5 modelos derivando casos de prueba | ninguno construyó un secreto de 35 caracteres; todos volcados a negativos | no usar casos derivados para aprobar |
| `comparar_extractores.py` | 5 modelos extrayendo la especificación de formato | sólo qwen2.5-coder la extrajo bien; las otras 3 erróneas las rechazaron las defensas | extractor = `qwen2.5-coder:7b` |
| `extractor_redacciones.py` | el extractor ante 5 redacciones de las dos tareas de formato + las 5 que no lo son | 10/10 bien; la redacción «que acepte…» se recupera con el reintento; antes del arreglo, tope 1 al identificador y 2 tareas en bucle 180 s | defensas de cantidades, 1 reintento, topes en el esquema |
| `comparar_segmentadores.py` | 5 modelos segmentando tarea / reglas / límites (27 hechos a mano) | qwen 27/27, gemma3 25, codegemma 25, mistral 23, llama3.2 22 | segmentador = qwen… |
| `efecto_reglas.py` | el coder con y sin las reglas segmentadas | codegemma 72 → 68/73 **con** reglas | …y segmentador **desactivado** |
| `banco_kv_hilos.py` | caché KV f16 vs q8_0 y `num_thread` | 7,28 → 6,21 GiB, +13 % generación; 12 hilos no gana con q8_0 | caché `q8_0`, hilos por defecto |
| `huella_memoria.py` | huella = peso + caché KV por ventana (tabla), en f16 | valida 3 puntos f16; los 7 (f16 + q8_0, error ≤ 2,6 %) están en `tests/test_niveles.py` | techos de `profiles/niveles.yaml` |
| `bateria_ab.py`, `vivo_ab_referencia.py` | el concilio completo, deepseek vs qwen de coder | qwen 25,8 min vs 44,8; ningún consenso en 4 corridas | reveló los defectos del concilio que arregló la v1 |

Los resultados en JSON que escriben algunos arneses van a `bench/resultados/`, que está en
`.gitignore`: son datos generados y pueden contener código escrito por modelos. Los números que
importan están en esta tabla y en `CHANGELOG.md`.

**Aviso sobre las cifras:** casi todas son **una corrida por condición** a temperatura 0. Con
temperatura 0 cada prompt da una salida fija, pero **distinto prompt, distinta salida**: se vio
a qwen acertar y fallar la misma función según el encuadre. Sirven para decidir entre opciones
claramente separadas, no para afinar diferencias de uno o dos casos.
