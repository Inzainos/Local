# legacy/ — tuberías retiradas en la v1

Retiradas el 2026-09-25. **No están borradas**: se movieron con `git mv`, así
que el historial se conserva y se pueden restaurar con otro `git mv`.

| pieza | qué era |
|---|---|
| `run_moe.py` + `engine/moe_captain.py` | Capitán (nemotron-mini) que elegía un experto de un pool y un auditor |
| `run_profile.py` + `engine/profile_pipeline.py` | investigador → coder → optimizador por perfil YAML |
| `profiles/*.yaml` | los perfiles de esas dos tuberías |
| `PERFILES_INDEPENDIENTES.md` | su documentación |

## Por qué se retiraron

Ninguna entrada viva las usaba —ni el bot de Telegram, ni el CLI, ni la web,
ni servicios, ni cron: comprobado antes de moverlas—, pero seguían siendo
ejecutables y **no tenían ninguno de los arreglos de la v1**:

- **Aprobaban por puntuación LEÍDA.** Sin verificador. Medido el 2026-09-24:
  la lectura del árbitro puso 92, 93 y 96 a tres códigos que rechazaban todos
  los tokens válidos, y 97–99 el 25 a otro que ni compilaba.
- **Llamaban a Ollama sin `num_ctx`.** El servidor tiene
  `OLLAMA_CONTEXT_LENGTH=262144`: cada llamada pedía la reserva de caché de la
  ventana completa, muy por encima de los 11,71 GiB del host.
- **nemotron-mini de capitán.** El operador lo reservó sólo para el portero.
- **Su capitán rellenaba en silencio**: si la clasificación salía del esquema
  devolvía la primera etiqueta con un aviso en el log, sin que quien llamaba
  pudiera saberlo.

Parchearlas a medias habría sido justo el problema que el operador señaló:
arreglar un camino y dejar los demás con la versión vieja.

## Lo que las sustituye

Todo pasa por `engine/orchestrator.py::run_consensus`, que desde la v1 intenta
primero la **vía directa** (una llamada al coder + verificación por ejecución)
y sólo escala al concilio si no pasa. El capitán por niveles
(`engine/turnos_ollama.py::elegir_area_y_nivel`) y el motor de turnos
(`engine/turnos.py`) son la evolución de estas tuberías; quedan para la v2.

Estos archivos **no se ejecutan tal cual**: sus imports apuntan a
`engine.moe_captain` / `engine.profile_pipeline`, que ya no están en `engine/`.
Es intencionado.
