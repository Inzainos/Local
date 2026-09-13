# System Health — 2026-09-10/11

Actualizado post ingest + restart (~18:31 CST). Detalle: `SESSION_2026-09-10.md`.

## Overall: OK (con seguimiento Delta)

| Área | Estado |
|------|--------|
| systemd sentinel-omega | active desde 18:30:00 CST PID 21847 |
| consensus-telegram / web | active |
| HTTP 8788/5174/8002 | 200 en sesión |
| Schumann vivo | **8.26 / 21.46** (ya no 7.83/0 falso) |
| Sismos | máx 2026-09-10 23:03 |
| Clima 2026 | 25 filas |
| Delta | bloqueo de writes all-zero; filas legacy en 0 permanecen |
| ONNX | regenerados Dev/Test/Prod incl. Loki en Prod |
| Lotería messaging | 0 matches en alert templates |
| Dashboard 6 tabs | en Dev/Test/Prod |

## Pendientes
- Delta completeness > 0 en próximo ciclo con datos reales
- Opcional `--entrenar` firmas
- Vite Prod vs Dev
