# ESTADO.md — set point del proyecto

> **Si entras a este proyecto a mitad de algo, empieza aquí.** Este archivo dice qué se está
> haciendo AHORA, qué se hizo y qué falta, para que un corte (falta de tokens, otra sesión, otro
> modelo) no deje a nadie sin saber dónde se quedó. **Se actualiza cada vez que algo avanza.**
> Si lo que dice aquí contradice al código, manda el código: verifícalo y corrige este archivo.

**Última actualización:** 2026-10-01 23:55. **v1 CERRADA** y en pie (verificado hoy: 253 tests,
servicios activos, `:8002/mini` 200, Ollama 200). **Hay un arreglo commiteado SIN desplegar**
(`89c96e2`, cola de alertas): el reinicio lo hace el operador. Lo que sigue es v2.
**Rama:** `local/concilio` (nunca push a `main`). **Operador:** Elán (responder en español).

---

## 1. Qué es y a dónde va

**Objetivo del operador** (en sus palabras): que los modelos locales sean «más precisos, sean
reales y no necesiten tanta auditoría», para aligerar la carga de la máquina y de los asistentes
que le ayudan. Quiere una **versión estable en ~2 días**, no en semanas, antes de volver a moverla.

**La idea que lo resuelve:** un modelo no decide si su código funciona **leyéndolo** — lo
**ejecuta**. Medido: la lectura del árbitro puso 92–99 a código roto.

Arquitectura, modelos y reglas: [`AGENTS.md`](./AGENTS.md). Mediciones: [`bench/README.md`](./bench/README.md).
Historial: [`CHANGELOG.md`](./CHANGELOG.md).

---

## 2. EN CURSO ahora mismo

### Servicios: corren la v1 + 3.0.1 + 3.0.2 + el botón de la Mini App (reiniciados 01-oct 22:07)
**PENDIENTE DE DESPLEGAR: el arreglo de la cola de alertas (`89c96e2`).** Está commiteado y probado,
pero los servicios siguen con el código de antes. Reiniciar = `sudo systemctl restart
consensus-telegram consensus-web` (lo corre el operador; no se toca systemd sin su orden).
`consensus-telegram` (bot) y `consensus-web` son **servicios del sistema** y cargan el código **al
arrancar**: cualquier cambio posterior no llega al teléfono ni a la web hasta reiniciarlos.
Comprobar qué código corren: `systemctl show consensus-telegram consensus-web -p ActiveEnterTimestamp`
contra `git log -1 --format=%ci`.
El aviso de tareas interrumpidas está vivo (en el journal: «sin tareas interrumpidas»), pero **no vio
la sesión cortada de las 13:05** del 25-sep: es del esquema 1 y `sesiones_interrumpidas()` ignora
esas a propósito. El aviso empieza a contar desde las sesiones creadas por este código.

| qué | estado | cómo retomarlo si se cortó |
|---|---|---|
| **v1.0-estable** | **ETIQUETADA** en `local/concilio`. Aceptación: cero consensos falsos en la 2.ª pasada y en la comprobación del mejor intento (`es_matricula`: el concilio llegó a 0/16 y se entregó el 15/16 de la vía directa) | `git show v1.0-estable` |
| **Desplegar** | **HECHO** 25-sep 09:46 | `journalctl -u consensus-telegram -n 50` |
| **1.ª tarea real (12:18)** | token con la redacción «que acepte…»: vía directa falló BIEN (codegemma escribió `len(token)==39 and isalnum()` dos veces); el concilio acertó en la ronda 1 pero se entregó «SIN CONSENSO 15/16» por un caso MAL construido (el extractor puso tope 1 al identificador; «un secreto» lo justificaba). **Arreglado en 3.0.1** (`88951e8`, ver CHANGELOG) y medido con `bench/extractor_redacciones.py` 10/10 | hecho: reinicio 13:04 |
| **2.ª tarea real (13:05)** | misma redacción, con el arreglo. La defensa **funcionó**: rechazó el tope 1 y el reintento construyó los 16 casos buenos. La vía directa falló bien (codegemma, 8/16 = la base). Concilio ronda 1: código que **no compila** (`from typing import str`) y el árbitro le había leído 92 → el verificador lo paró. Ronda 2: código CORRECTO (16/16, re-verificado a mano el 25-sep 13:35) pero **un reinicio de Windows a las 13:16 cortó la tarea mientras el árbitro lo revisaba**: no se entregó nada y el operador no recibió aviso | `data/sessions/91bce515.concilio` (última escritura 13:16) y `journalctl -b -1 -u consensus-telegram --since 13:05` |
| **3.ª tarea real (14:24)** | **✅ CERRÓ BIEN.** Token con la redacción del operador: vía directa falló (codegemma, 8/16 = la base) y escaló; el concilio acertó en la **ronda 1** y el verificador dio **16/16 = consenso 100**. 9 minutos. Re-verificado a mano el 25-sep 14:38: 16/16. La sesión quedó `cerrado: terminada` y el aviso de interrumpidas no reporta nada | `journalctl -u consensus-telegram --since 14:24` |
| **Aprendizaje de errores** | idea del operador (25-sep, ver apartado 4, v2): que el sistema aprenda de sus aciertos y fallos como los modelos ONNX de Sentinel | sin empezar |

**1.ª pasada de aceptación** (antes de `2565dfc`): 7 tareas en 12,4 min, **1 consenso falso**
(`es_matricula` aprobada con 15/16 por el umbral de 85). Corregido: con casos de especificación
se exigen TODOS. El hecho que archivó ese falso aprobado está en `knowledge_facts_cuarentena` (#9).

## 3. Qué se hizo (24–25 sep, ~40 commits) — lo esencial

- **Verificador por ejecución** con casos derivados del ENUNCIADO; para validadores de formato,
  el modelo extrae la especificación y **Python construye** los casos.
- **Vía directa**: una llamada al coder + verificar; concilio sólo si falla. Bot, CLI y web
  muestran «Verificado por ejecución» / «SIN VERIFICAR» / resultado del concilio.
- **Coder `codegemma:7b`** (medido), extractor `qwen2.5-coder:7b`, nemotron-mini sólo portero.
- **Ollama con caché `q8_0`** + flash attention (variables de usuario de Windows).
- **Memoria**: filtro de relevancia, archiva sólo consenso real, 8 hechos falsos en cuarentena.
- **Frenos** del concilio: entregable idéntico, o 4 rondas sin mejora por encima del ruido.
- **Tuberías viejas** retiradas a `legacy/`. **Arneses de medición** en `bench/`.
- Documentación reescrita para describir lo que existe.

Detalle y porqués: `CHANGELOG.md` y los mensajes de commit (cada uno explica su medición).

---

## 4. Qué falta

**La v1 está cerrada.** Queda medido, de punta a punta y en producción: la vía directa rechaza lo
que no funciona, el concilio lo arregla, el verificador lo confirma ejecutándolo y la sesión se
cierra. Lo primero de la v2 sigue siendo el **segundo intento con otro modelo**: codegemma falla
con esta redacción las dos veces, y eso son 8 minutos de concilio que qwen podría ahorrar.

**Para cerrar la v1** — HECHO:
1. ~~2.ª pasada de aceptación con cero consensos falsos~~ — hecha.
1b. ~~Mejor intento verificado~~ — construido (`51c0ba4`); falta verlo en vivo con `es_matricula`.
2. ~~CHANGELOG 3.0.0~~ — hecho. 3. ~~Etiqueta `v1.0-estable`~~ — hecha.
4. ~~Desplegar~~ — hecho el 25-sep 09:46.

**Hueco del 25-sep 13:16 (reinicio de Windows), AVISO YA HECHO en 3.0.2 (`226bbba`):** el bot avisa al
arrancar de las tareas que quedaron a medias, y sólo las marca cerradas si el aviso salió. Lo que
sigue sin existir es **reanudar**: la tarea hay que volver a mandarla a mano. Reanudarla de verdad
exige decidir desde dónde (el código de la última ronda está en el `.concilio`) y no está medido.

**v2** (acordado con el operador que queda fuera de la v1). Orden recomendado tras medir: primero
«segundo intento con otro modelo» (codegemma repitió el mismo código en sus dos intentos de
`es_matricula`), luego la opción C, luego rediseñar el concilio para código (empeoró 15/16 → 0/16).
- **Aprender de los propios errores** (idea del operador): casos fallidos como pruebas de
  regresión permanentes, marcador de acierto por modelo y tipo de tarea (como el Juez de
  Sentinel), soluciones verificadas como ejemplos, y feedback del operador donde no hay nada que
  ejecutar. Sólo con resultados VERIFICADOS: los hechos falsos archivados envenenaron la memoria.
- **Opción C**: verificar tareas que no son validadores de formato con **relaciones** sin oráculo
  (`f('1h30m') == f('1h') + f('30m')`, entradas inválidas → 0). Hoy salen «SIN VERIFICAR».
- **Investigación/análisis**: no hay nada que ejecutar; la independencia no está resuelta ahí.
- **Motor de turnos + niveles + portero** (`engine/turnos*.py`, `profiles/niveles.yaml`):
  escritos y probados, no cableados.
- **Índice vectorial** con `nomic-embed-text` (el filtro de relevancia actual es léxico).
- **Segmentación** para prompts desordenados (conversacionales, por voz): hipótesis sin medir;
  con enunciados limpios empeoró al coder.
- **Módulo de RAM**: el operador podría cambiar el de 4 GiB por uno de 8 (host 11,7 → 16 GiB,
  canal doble completo). Es lo único que haría caber `deepseek-r1:14b` o retener dos modelos.

**Pendientes de Sentinel Omega** (otro repo: `/home/deamon/workspaces`), de sesiones anteriores:
bitácora del día, por qué alfa1 reconoce el 100 % de los eventos (5 de 9 bots saturados en ~1,0),
`tbl_trends_vivo` con 0 filas.

---

## 5. Cómo trabaja el operador (preferencias medidas en la práctica)

- **Decide midiendo, no opinando.** Cuando pide elegir («el mejor modelo»), quiere que se mida y
  se aplique **sin volver a preguntar**. Si la medición contradice una decisión ya tomada, se
  revierte y se explica (así se desactivó el segmentador).
- **Barrido de hermanos**: cuando se arregla algo en un sitio, revisar el mismo patrón en los
  demás. Lo pidió expresamente: «nos enfocamos en un código y los demás siguen iguales».
- **Menos correcciones terminológicas**: corregir sólo lo que cambia la decisión.
- **Confirmar antes** de reiniciar servicios compartidos (Ollama lo usan otras herramientas suyas:
  opencode, hermes) o de tocar Sentinel / systemd / la DB de producción.
- Nunca push a `main`; secretos sólo por entorno; cero datos sintéticos; migraciones hacia delante.

---

## 6. Documentación fuera de este repositorio

- `/home/deamon/AGENTS.md` (el que leen todas las herramientas) se actualizó el 25-sep con la v1.
  **`/home/deamon` no es un repositorio git**: ese cambio no queda versionado.
- Sentinel Omega: estado canónico en `/home/deamon/workspaces/estado/` (`REPORTE.md`, historial
  en `estado/historial/AAAA/MM/`). Última bitácora escrita: `BITACORA_2026-09-20.md`.
- Móvil (DeamonX): usa `concilio-lightest:latest` por túnel SSH al mismo Ollama; el reinicio de
  Ollama del 25-sep (caché `q8_0`) también le afecta.
- El operador usa este Ollama con otras herramientas (`opencode`, `hermes`): cualquier cambio del
  servidor les llega.

## 7. Trampas del entorno (cada una costó tiempo)

- **Ollama corre en el host Windows**, no en WSL: `free` de WSL no ve su memoria. Medir con
  `/api/ps` y `powershell.exe Get-CimInstance Win32_OperatingSystem`.
- **`pkill -f patrón` o `pgrep -f`** con un patrón que aparece en tu propia orden **mata tu
  shell** (exit 144). Usar `ps aux | grep '[p]atron'` y matar por PID.
- **Tests con `.venv/bin/python`**, no `/usr/bin/python3` (el guardián de pyflakes lo exige).
- **Logs de arneses con tubería** llegan con retraso; la fuente fiable del avance son las pizarras
  en `data/shared_memory.db`.
- **`grep -E "-> ..."`**: un patrón que empieza por `-` se lee como opción; usar `-e`.
- Revertir la caché de Ollama: `C:\Users\elanz\AppData\Local\Temp\ollama_revertir.ps1`.

## 2026-09-27 (noche) — Telegram del Sentinel (T)

El Sentinel usaba el token viejo de SismoBio_Bot (401). Se rotó `deploy/.env` a las
19:42 con el token válido (`600`, respaldos en `~/t_scripts/respaldos/`). Los avisos
directos del día venían del Sentinel de root, que ya está enmascarado. No hay
resúmenes mientras dure el rebuild. Detalle en
`/home/deamon/workspaces/estado/TELEGRAM_2026-09-27.md`.

## 2026-10-01 (noche) — revisión del proyecto y arreglo de la cola de alertas

**Lo que se verificó** (evidencia directa, no lectura): 253 tests pasan en 5,2 s con cero saltados
(`.venv/bin/python -m pytest tests/ -q -rs`), ambas units activas desde las 22:07 (el bot tardó
3,5 min en terminar de arrancar: «Bot iniciado — polling» a las 22:10:37), `:8002/mini` responde 200, Ollama responde 200 en `/api/tags` sin modelos en VRAM,
el bot no reporta tareas interrumpidas y el botón de la Mini App apunta a la URL viva del túnel.

**Lo que se arregló**

| commit | qué | desplegado |
|---|---|---|
| `199fcd7` | versionar `registrar_boton_mini_app`, que corría desde el 27-sep sin commitear (los servicios de hoy ya lo cargaron, pero HEAD seguía en el 25-sep y `git show v1.0-estable` no reproducía producción) | **sí**, ya corría |
| `89c96e2` | la cola de alertas perdía avisos: `pop_batch()` los borraba del archivo antes de enviarlos. Añade marca de **en vuelo** + recuperación al arrancar, **tope de 5 reintentos** con `alert_queue_dead.json` (antes un aviso irrecibible tapaba la cola FIFO para siempre) y **entrega parcial** que ya no se da por entregada. Validado por mutación 4/4 | **NO** — hace falta reiniciar los servicios |
| — | permisos: `telegram_bot.py` (666) y `agents/{coder,optimizer}.py` (777) → 755. Código del camino vivo reescribible por cualquier otro uid. Git no lo ve (el bit de ejecución no cambió) | sí (es en disco) |

El arreglo de la cola es **compatible en los dos sentidos** mientras no se reinicie: un aviso recién
encolado se sigue escribiendo con el esquema de antes (`_a_dict` omite los campos nuevos cuando no
dicen nada), porque el bot vivo tiene el módulo viejo en memoria y el Sentinel importa
`alert_queue.py` **por ruta absoluta** desde sus propios procesos
(`workspaces/sentinel_omega/infrastructure/api/telegram.py:34`).

**Lo que queda abierto (medido, sin arreglar)**

1. **El botón Mini App depende de un túnel efímero y de edición a mano.** Esta noche el túnel rotó de
   `motion-warrior-lighting-tab` (22:07:01) a `metals-june-kiss-mate` (22:07:05) y hubo que editar
   `.env` (22:07:10) y reiniciar el bot (22:10:37) para que el botón apuntara bien: dos URLs en
   3,5 min. `TELEGRAM_WEBAPP_URL` se lee **al importar** y el botón sólo se re-registra **al
   arrancar**, así que la próxima rotación lo deja muerto sin aviso. Arreglo de fondo: túnel con
   nombre (hostname estable) o leer la URL del túnel al registrar.
2. **Los contadores de la cola se pisan entre procesos.** `total_sent` 2163 vs `total_enqueued` 92 no
   es antigüedad (ambas claves nacieron en `f4abb65`): `_save_stats()` escribe el dict completo de su
   propia copia en memoria, así que cada escritura del bot revierte los `total_enqueued` que sumó el
   Sentinel y al revés. Lo que sí es fiable es el tamaño de los archivos (`size`, `en_vuelo`,
   `descartados`), que se cuenta leyendo. Arreglo: releer stats dentro del lock antes de sumar.
3. **`source="sentinel"` está fijo** en `queue_alert()` para toda la API pública: la cola no puede
   decir quién produjo un aviso, y todo lo del Sentinel llega además con prioridad MEDIUM fija
   (`infrastructure/api/telegram.py:191`), perdiendo su severidad real.
4. **La rama local va 73 commits por delante de `origin/local/concilio`**: la única copia de la v1 y
   de todo esto es este disco.
5. **11 MB de copias viejas en el árbol del servicio**: `data/shared_memory.db.pre_cuarentena_*` (×2)
   y `telegram_bot.py.bak.*` (×4). No están en git; conviene moverlas fuera del directorio que lee
   el bot.
