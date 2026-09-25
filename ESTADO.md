# ESTADO.md — set point del proyecto

> **Si entras a este proyecto a mitad de algo, empieza aquí.** Este archivo dice qué se está
> haciendo AHORA, qué se hizo y qué falta, para que un corte (falta de tokens, otra sesión, otro
> modelo) no deje a nadie sin saber dónde se quedó. **Se actualiza cada vez que algo avanza.**
> Si lo que dice aquí contradice al código, manda el código: verifícalo y corrige este archivo.

**Última actualización:** 2026-09-25, tras la 2.ª pasada de aceptación (cero consensos falsos).
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

### ⚠ Lo más importante: los servicios corren código VIEJO
`consensus-telegram` (bot) y `consensus-web` son **servicios del sistema** y cargan el código al
arrancar. El 25-sep el bot corría el código del **24 por la mañana** (antes del verificador) y la
web el del **20**. Nada de la v1 llega al teléfono hasta reiniciarlos, y el bot viejo **puede
archivar como «hecho aprobado» cualquier lectura ≥ 85** (la memoria envenenada que se limpió).
Regla: no se toca systemd sin orden del operador. **Desplegar la v1 =**
`sudo systemctl restart consensus-telegram consensus-web` (lo decide y lo corre el operador).

| qué | estado | cómo retomarlo si se cortó |
|---|---|---|
| **Aceptación v1, 2.ª pasada** | **HECHA: cero consensos falsos**, 26,0 min. `validar_token` verificada 16/16 (1,1 min); `a_segundos`, `es_palindromo`, `es_bisiesto`, `a_romano`, `es_ipv4` sin verificar y las cinco correctas por la vara independiente; `es_matricula` escaló al concilio y no cerró (14,3 min) | — |
| **Mejor intento verificado** (`51c0ba4`) | construido y probado; **corriendo su verificación en vivo** con `bench/aceptacion.py es_matricula`: debe entregar el 15/16 de la vía directa, no el 8/16 del concilio | relanzar `.venv/bin/python bench/aceptacion.py es_matricula` con Ollama libre; mirar la vara y que la síntesis diga «mejor intento medido» |
| **CHANGELOG 3.0.0** | borrador fuera del repo; cifras ya disponibles salvo la del mejor intento | reescribir desde `git log --since=2026-09-24` y el apartado 3 |
| **Etiqueta `v1.0-estable`** | lista para poner en cuanto el mejor intento se verifique en vivo | `git tag -a v1.0-estable` en `local/concilio`, sin push |

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

**Para cerrar la v1** (antes de la etiqueta):
1. ~~2.ª pasada de aceptación con cero consensos falsos~~ — hecha.
1b. ~~Mejor intento verificado~~ — construido (`51c0ba4`); falta verlo en vivo con `es_matricula`.
2. CHANGELOG 3.0.0 con sus cifras, y la cifra del README si cambió.
3. Commit + etiqueta `v1.0-estable`.

**v2** (acordado con el operador que queda fuera de la v1):
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
