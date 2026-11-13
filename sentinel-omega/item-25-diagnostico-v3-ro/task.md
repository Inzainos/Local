# Task List — Plan de Persistencia Sentinel Omega

## Fase 0 — Acciones Inmediatas (sin cambios de código)
- [/] **Refetch USGS** — recuperar 30 días de sismos faltantes (`sismos_refetch_recent.py --days 30`)
- [ ] **Verificar resultado** — confirmar sismos ingresados en TBL_HISTORICO_SISMICO

## Fase 1 — LOCF Activado (~3h)
- [ ] Leer schema real de `tbl_locf_cache` y `_migrate_add_missing_columns`
- [ ] Agregar `update_locf_cache()` y `get_locf_cache()` en `repository.py`
- [ ] Activar escritura LOCF en `data_pipeline.py` por cada fuente (alfa1, beta1, beta2, delta, omega)
- [ ] Activar lectura LOCF como fallback en cada conector
- [ ] Corregir ingesta de `protones` desde OMNI2 en conector alfa1

## Fase 2 — Refetch Automático (~3h)
- [ ] Añadir `check_api_lags()` en `mantenimiento.py`
- [ ] Orquestar `sismos_refetch_recent` desde barrido diario si lag > 7 días
- [ ] Orquestar `clima_gapfill_2026` si lag clima > 7 días
- [ ] Stub para refetch delta/psique si lag > 7 días

## Fase 3 — APIHealthTracker (~2h)
- [ ] Clase `APIHealthTracker` en `layer_runners.py`
- [ ] Persistir `api_health_json` en `tbl_salud_sistema`
- [ ] Exponer en `/api/health` del dashboard React

## Verificación
- [ ] Tests pasan (`PYTHONPATH=. python -m pytest tests/ -q`)
- [ ] LOCF cache tiene entradas después de un ciclo
- [ ] Sismos recuperados visibles en DB
- [ ] Dashboard muestra estado API
