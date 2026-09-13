# Pipeline de auditoría — Sistema Omega

Diseño completo de auditoría a nivel de base de datos para Sentinel Omega
en PostgreSQL. Scripts SQL en `infrastructure/database/audit/`, guías en
`docs/audit/`.

## Scripts SQL (`infrastructure/database/audit/`)
| Archivo | Contenido |
|---|---|
| `01_schema.sql` | Esquema `audit`, tabla `audit_logs` particionada, índices, roles |
| `02_functions_triggers.sql` | Función `fn_current_app_user`, trigger genérico `fn_audit_trigger` (INSERT/UPDATE/DELETE) |
| `03_truncate_trigger.sql` | Trigger de nivel de statement para `TRUNCATE` |
| `04_partition_maintenance.sql` | Rotación de particiones, tablespace dedicado, verificación de integridad (`pg_cron`) |
| `05_event_trigger_auto_instrument.sql` | Event trigger DDL que auto-instrumenta tablas nuevas con auditoría |
| `06_data_masking.sql` | Enmascaramiento de columnas sensibles antes de serializar a JSONB |

## Guías (`docs/audit/`)
| Archivo | Contenido |
|---|---|
| `01_pgbouncer_pooling.md` | Cómo preservar la identidad del actor bajo pooling de conexiones |
| `02_cold_storage_export.md` | Exportación a frío, retención, respaldo CDC, monitoreo |
| `03_incident_runbook.md` | Procedimiento ante ruptura de la cadena de integridad |
| `04_investigation_queries.md` | Queries listas para investigar cambios históricos |

## Pendientes conocidos (no bloqueantes para el despliegue inicial)
- Backup/restore físico (`pg_basebackup`/WAL archiving) del esquema `audit`
  como tal, separado del export a frío (que es para retención, no DR).
- Benchmark de overhead del trigger por fila bajo carga real (5 agentes,
  bloques de 6h) — pendiente de ejecutar con `pgbench` antes de producción.

## Orden de aplicación recomendado
```bash
psql -f 01_schema.sql
psql -f 02_functions_triggers.sql
psql -f 03_truncate_trigger.sql
psql -f 06_data_masking.sql
psql -f 04_partition_maintenance.sql
psql -f 05_event_trigger_auto_instrument.sql
```
