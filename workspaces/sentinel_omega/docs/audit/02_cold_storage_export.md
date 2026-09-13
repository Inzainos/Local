# Auditoría — Exportación a almacenamiento frío

## Flujo

1. `pg_cron` desprende (`DETACH PARTITION`) particiones de
   `audit.audit_logs` con más de 60 días de antigüedad
   (ver `infrastructure/database/audit/04_partition_maintenance.sql`).
2. Un worker externo (cron del sistema operativo o Airflow) detecta
   particiones desprendidas y las exporta:

```sql
COPY audit.audit_logs_2026_04 TO PROGRAM
  'zstd > /tmp/audit_2026_04.csv.zst' WITH CSV HEADER;
```

3. El worker sube el archivo a S3 (o lo carga en ClickHouse/BigQuery para
   correlacionar con eventos NOAA/USGS a gran escala).
4. Verifica integridad comparando la cadena de `row_hash` exportada contra
   la original, y solo entonces ejecuta `DROP TABLE audit.audit_logs_2026_04`.

## Retención y borrado (Brecha #8)

- Retención mínima recomendada para datos vinculados al corpus SNT
  (reconstruction_real/v4) y al preprint en SSRN/PLOS ONE: **7 años**,
  alineado con prácticas estándar de reproducibilidad científica, salvo
  que el journal o la institución exijan un plazo distinto.
- Los datos exportados a frío se cifran en reposo (SSE-S3 o equivalente)
  y se versiona el bucket para evitar borrado accidental.
- Purga controlada: requiere aprobación explícita (doble verificación)
  antes de eliminar cualquier export más allá del período de retención.
  Nunca automatizar el `DROP`/borrado final sin paso manual de confirmación.

## Respaldo CDC complementario (Logical Decoding)

Como segunda línea de defensa, independiente de los triggers de
aplicación (cubre DDL directo, bypass accidental, o auditoría sin tocar
el código de la app):

```sql
ALTER SYSTEM SET wal_level = logical;
SELECT pg_create_logical_replication_slot('omega_audit_slot', 'wal2json');
```

Consumido por Debezium hacia Kafka → S3/ClickHouse. No sustituye los
triggers (que dan contexto de negocio como `user_id` lógico), pero sirve
de respaldo a nivel de WAL si los triggers fallan o se desactivan sin
autorización.

## Monitoreo del pipeline

Alertar si:
- La partición `audit_logs_default` recibe filas (indica que el job de
  creación de particiones futuras falló).
- Una partición desprendida tarda más de 24 horas en ser exportada
  (indica que el worker de exportación se está atrasando respecto al
  volumen de escritura real de Sentinel Omega).
