# Atajos de iOS — Roy en el bolsillo

Dos Atajos para la app **Atajos (Shortcuts)** de iPhone/iPad. Como el repo es
público, el de lectura no necesita ningún token.

## Atajo 1: "Roy Reporte" (leer y guardar)

Abre Atajos → + → agrega estas acciones en orden:

1. **Obtener contenido de URL**
   `https://raw.githubusercontent.com/Inzainos/workspaces/main/estado/REPORTE.md`
2. **Mostrar notificación** — título: `🌍 Roy`, cuerpo: *Contenido de URL*
   (te asoma el fantasma y el muro sin abrir nada)
3. **Guardar archivo** — destino: iCloud Drive → carpeta `Roy/`,
   nombre: `reporte-` + *Fecha actual* + `.md`, con "Preguntar dónde
   guardar" APAGADO

Con eso cada corrida te notifica el estado Y guarda el corte con fecha.
(El historial completo de todos modos vive en git: cada reporte es un commit.)

## Atajo 2: "Roy Despierta" (disparar un ciclo al momento)

Para cuando sientas que está temblando y quieras un ciclo YA, sin esperar
la media hora:

1. En Safari: github.com → Settings (tu perfil) → Developer settings →
   **Fine-grained tokens** → Generate new token:
   - Repository access: *Only select repositories* → `workspaces`
   - Permissions → Actions: **Read and write** (nada más)
   - Copia el token (empieza con `github_pat_...`)
2. En Atajos → + →
   - **Texto**: pega el token (queda guardado solo en tu dispositivo)
   - **Obtener contenido de URL**:
     `https://api.github.com/repos/Inzainos/workspaces/actions/workflows/roy-vigilante.yml/dispatches`
     - Método: **POST**
     - Cabeceras: `Authorization` = `Bearer ` + *Texto*,
       `Accept` = `application/vnd.github+json`
     - Cuerpo (JSON): `{"ref": "main"}`
   - **Mostrar notificación**: `🛰 Ciclo disparado — reporte en ~4 min`
3. Opcional: encadena al final el Atajo 1 con una **Esperar** de 240 s
   para que te llegue el reporte fresco solito.

## Automatización (que corra solo)

Atajos → Automatización → + → **Hora del día** → escoge la hora →
Repetir: *Diariamente* → acción: ejecutar "Roy Reporte" → **Ejecutar
inmediatamente** (sin preguntar).

iOS no permite "cada 25 min" nativo — pero no hace falta: **el vigilante de
GitHub ya corre cada 30 min solo**. Crea 3-4 automatizaciones en tus horas
clave (ej. 7:00, 13:00, 19:00, 23:00) para la notificación resumen, y el
widget del Atajo en la pantalla de inicio para consultarlo con un toque.

## Seguridad

- El atajo de LECTURA no usa ningún token.
- El token del Atajo 2 es de alcance mínimo (solo Actions de este repo) y
  vive únicamente en tu dispositivo. Si se filtra, se revoca en GitHub y ya.
- Nunca pongas el token en el repo ni en chats.
