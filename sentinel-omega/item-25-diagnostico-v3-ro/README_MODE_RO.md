# Paquete ítem 25 — `diagnostico_v3.py` en modo solo lectura

**Encargo del Concilio:** "validar `diagnostico_v3.py` contra la DB actual,
sin ejecutar con escritura" (decisión 25 de Elán, 2026-11-12).
**Rama de entrega decidida por Elán 2026-11-12 ~19:23:** `Local/local/concilio`
(en el repo `Inzainos/Local`). Este paquete queda LOCAL en esta fase; la
subida a esa rama NO se hizo aquí (no ordenada en esta fase).

## Qué se parcheó (solo 2 cosas, nada más)

1. **Apertura solo lectura:** `sqlite3.connect(DB)` →
   `sqlite3.connect(f"file:{DB}?mode=ro", uri=True)` (`diagnostico_v3.py:10`).
   Con `mode=ro` SQLite rechaza cualquier escritura con
   `OperationalError: attempt to write a readonly database` y NO crea el
   archivo si la ruta no existe.
2. **Path corregido** a la DB viva actual
   (`/home/deamon/Sentinel_Omega/sentinel_omega/data/SENTINEL_OMEGA_PRO.db`,
   `diagnostico_v3.py:9`). El original apuntaba al path viejo
   `/home/deamon/workspaces/sentinel_omega/data/...`.

El script no contiene ninguna otra escritura: grep de
`INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|PRAGMA|commit()` sobre el original =
sin coincidencias (solo SELECTs + prints).

## Hashes (ver `MANIFEST.sha256`; verificar con `sha256sum -c MANIFEST.sha256`)

- `diagnostico_v3.py` (parcheado): `a0095797c9ba25fcc71501f9c1ab1531d2d9d92e0ec3ce2356de3f6529455c86`
- `diagnostico_v3.py` (prístino, antes del parche):
  `8b1444821ac753c9c8d4e2d3c459631544ce3dfc577a6490a54b70042590a0a0`
  (respaldo en `respaldos-tuning/2026-11-12-f2-d6-25-j3/diagnostico_v3.py.PRISTINO-2026-11-12`)
- `task.md`: `dda9e05fdd900f1142d5eb4e3d11e8ecca95d6af31c935cce2f3e736bbda5b1d`
- `implementation_plan.md`: `eae2d532a906226d8a42dc7afe6bbafebe669ecffe0d055f4c42972cd838cffe`

## Verificaciones hechas 2026-11-12 ~19:25 CST

- `python3 -m py_compile diagnostico_v3.py` → OK.
- **Prueba de solo-lectura (en deamonx):** con la misma URI del parche, un
  INSERT falla con `attempt to write a readonly database`; control con
  conexión plana RW sobre la misma copia: el INSERT sí entra (prueba que es
  `mode=ro` lo que bloquea, no los permisos del archivo).
- **Corrida de humo contra copia en /tmp:** DB mínima con las 14 tablas que
  lee el script (1 fila por tabla) → exit 0, salida completa hasta
  `VEREDICTO DE ALERTA`, sha256 de la copia idéntico antes/después.
- **Corrida contra la DB viva (mode=ro, sin escritura):** el archivo parcheado
  abre la DB real y lee (3,507 registros en `TBL_PRECURSORES_COSMICOS`,
  lag 1 min), PERO se detiene en `diagnostico_v3.py:58` con
  `TypeError: unsupported format string passed to NoneType.__format__`:
  `AVG(schumann_hz)` es NULL en la DB actual (verificado por consulta ro:
  `3507|0|` — 0 valores no-nulos de `schumann_hz`). Es un bug PRE-EXISTENTE
  del script (formatea el AVG como float sin blindar None), NO del parche:
  el fallo está en un `print` posterior a SELECTs exitosos y el modo de
  conexión no puede cambiar que el AVG sea NULL (INV-1 ya midió hz 100%
  NULL). **El Concilio debe saberlo antes de validar:** con la DB actual el
  script no llega al veredicto sin blindar los AVG nulos (líneas 58 y
  siguientes que formatean `r["ash"]` / `r["asa"]`). No se corrigió aquí
  (fuera del alcance ordenado: solo mode=ro + path).

## Uso

```bash
python3 diagnostico_v3.py   # abre la DB viva en mode=ro; no escribe nada
```
