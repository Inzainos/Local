# Sentinel Omega — Fixes completos de sesión (2026-08)

Paquete **íntegro** de todos los cambios de la sesión de auditoría/corrección.
Destinado a revisión por otra IA: integridad, lógica, faltantes, documentación.

## Cómo aplicar el paquete completo

```bash
cd workspaces   # repo Inzainos/workspaces
git pull
# Extraer el tar COMPLETO (disponible en artifacts / Drive)
tar xzf sentinel_omega_COMPLETO_sesion.tar.gz
# revisar git status / diff
git add -A
git commit -m "feat(sentinel): sesión completa — LOCF, ONNX+Omega, Juez 2h, dual-ask, Telegram, lags, dashboard"
git push
```

## Schema v11 (importante)

Si `schema.py` aparece como loader self-expanding, los parts completos están en:
- `sentinel_omega/infrastructure/database/schema_parts/schema_part_*.b64`

Si los parts están incompletos en GitHub, restaurar desde el tar:

```bash
tar xzf sentinel_omega_COMPLETO_sesion.tar.gz sentinel_omega/infrastructure/database/schema.py
# o copiar schema_parts_v11 desde artifacts
```

El loader en `schema.py` hace:
1. Lee todos los `schema_part_*.b64`
2. Junta + base64 decode + zlib decompress
3. exec del módulo completo (SCHEMA_VERSION=11, SCHEMA_SQL, init_database, get_connection)

## Checklist de features incluidos

- [x] ONNX models bootstrap + train_from_db (6 agentes + Omega)
- [x] LOCF persistente (tbl_locf_cache + repository fallback)
- [x] Parallel fetches en data_pipeline
- [x] DB + live training Alfa-2
- [x] Volcado 24h vivo → histórico + cascada (schumann_vivo → enjambre_telemetria)
- [x] Omega spatial bot sin Shadow DOM bias + dual-ask voting + reference gate
- [x] Juez cada 2h + castigo/reforzar por bot
- [x] Lags dinámicos desde 1994 (sin tope 14d)
- [x] Catálogo multi-evento (sismos/erupciones/tsunami proxy)
- [x] Dashboard tabs Alfas/Betas/Omega/Padre/Juez/Eventos
- [x] Telegram Centinela V2 (gated, heartbeat, dual-ask, env-only)
- [x] ephem astronomy
- [x] Schema v11 + migrate_v11

## Archivos críticos de la sesión

- infrastructure/database/schema.py (v11)
- infrastructure/database/repository.py (save_locf/load_locf)
- infrastructure/pipeline/data_pipeline.py (LOCF fallback)
- infrastructure/pipeline/mantenimiento.py (volcado 24h)
- infrastructure/pipeline/verificacion.py (RITMO_HORAS=2)
- infrastructure/pipeline/layer_runners.py (Omega + agent_signals)
- layers/geodynamic/padre/agent.py (dual-ask)
- infrastructure/api/telegram.py (Centinela V2)
- launcher.py (agent_signals + ventana_h + verificar_juez)
- models/train_onnx_bootstrap.py + train_onnx_from_db.py
- infrastructure/dashboard/app.py (actor tabs)
