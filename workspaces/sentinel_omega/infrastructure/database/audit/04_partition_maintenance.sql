-- ============================================================
-- Sentinel Omega — Auditoría: Mantenimiento de particiones
-- Tablespace dedicado + rotación automática vía pg_cron
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Tablespace dedicado en disco separado del OLTP operativo
-- (ajustar ruta física según el host real)
-- CREATE TABLESPACE audit_ts LOCATION '/mnt/ssd_audit/pgdata_audit';
-- ALTER TABLE audit.audit_logs_2026_07 SET TABLESPACE audit_ts;

-- Crea la partición del mes siguiente, todos los días a las 03:00
SELECT cron.schedule(
    'audit_create_next_partition',
    '0 3 * * *',
    $$
    DO $do$
    DECLARE
        next_month DATE := date_trunc('month', now() + interval '1 month');
        part_name  TEXT := 'audit_logs_' || to_char(next_month, 'YYYY_MM');
    BEGIN
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS audit.%I PARTITION OF audit.audit_logs
             FOR VALUES FROM (%L) TO (%L)',
            part_name, next_month, next_month + interval '1 month'
        );
    END $do$;
    $$
);

-- Desprende particiones de más de 60 días, cada domingo a las 02:00.
-- El worker externo (ver docs/audit/05_cold_storage_export.md) procesa
-- la partición desprendida y solo entonces ejecuta DROP TABLE.
SELECT cron.schedule(
    'audit_detach_old_partitions',
    '0 2 * * 0',
    $$
    DO $do$
    DECLARE
        cutoff DATE := date_trunc('month', now() - interval '60 days');
        part_name TEXT := 'audit_logs_' || to_char(cutoff, 'YYYY_MM');
    BEGIN
        EXECUTE format('ALTER TABLE audit.audit_logs DETACH PARTITION audit.%I', part_name);
    END $do$;
    $$
);

-- Verificación de integridad de la cadena de hashes, cada 30 minutos.
-- Si el conteo es mayor a 0, la cadena está rota: investigar de inmediato
-- (ver docs/audit/06_incident_runbook.md).
SELECT cron.schedule(
    'audit_integrity_check',
    '*/30 * * * *',
    $$
    SELECT count(*) FROM (
        SELECT audit_id, row_hash, prev_row_hash,
               lag(row_hash) OVER (PARTITION BY table_name ORDER BY audit_id) AS expected_prev
        FROM audit.audit_logs
        WHERE created_at > now() - interval '1 day'
    ) t
    WHERE prev_row_hash IS DISTINCT FROM expected_prev;
    $$
);
