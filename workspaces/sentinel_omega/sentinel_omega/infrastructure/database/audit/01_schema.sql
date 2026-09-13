-- ============================================================
-- Sentinel Omega — Auditoría: Esquema base
-- Tabla AuditLogs particionada + roles de acceso
-- ============================================================

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TYPE audit.operation_type AS ENUM ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE');

-- ============================================================
-- Tabla particionada por rango de fecha (mensual)
-- ============================================================
CREATE TABLE audit.audit_logs (
    audit_id          BIGINT GENERATED ALWAYS AS IDENTITY,

    -- Identidad del actor
    user_id           UUID            NOT NULL,
    db_role           TEXT            NOT NULL DEFAULT current_user,
    application_name  TEXT            DEFAULT current_setting('application_name', true),
    client_addr       INET,

    -- Objeto afectado
    schema_name       TEXT            NOT NULL,
    table_name        TEXT            NOT NULL,
    record_pk         TEXT            NOT NULL,
    operation         audit.operation_type NOT NULL,

    -- Estado del dato (ver 07_data_masking.sql para columnas sensibles excluidas)
    old_value         JSONB,
    new_value         JSONB,
    changed_fields    TEXT[],

    -- Trazabilidad transaccional
    txid              BIGINT          NOT NULL DEFAULT txid_current(),
    statement_ts      TIMESTAMPTZ     NOT NULL DEFAULT statement_timestamp(),
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT clock_timestamp(),

    -- Cadena de integridad tipo ledger
    row_hash          TEXT            NOT NULL,
    prev_row_hash     TEXT,

    PRIMARY KEY (audit_id, created_at)
) PARTITION BY RANGE (created_at);

COMMENT ON TABLE audit.audit_logs IS
  'Bitácora inmutable de auditoría del Sistema Omega. Particionada mensualmente.';

-- Partición inicial + partición default como red de seguridad
CREATE TABLE audit.audit_logs_2026_07
    PARTITION OF audit.audit_logs
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE audit.audit_logs_default
    PARTITION OF audit.audit_logs DEFAULT;

-- ============================================================
-- Índices
-- ============================================================
CREATE INDEX idx_audit_table_record   ON audit.audit_logs (table_name, record_pk);
CREATE INDEX idx_audit_user           ON audit.audit_logs (user_id, created_at DESC);
CREATE INDEX idx_audit_txid           ON audit.audit_logs (txid);
CREATE INDEX idx_audit_new_value_gin  ON audit.audit_logs USING GIN (new_value jsonb_path_ops);
CREATE INDEX idx_audit_old_value_gin  ON audit.audit_logs USING GIN (old_value jsonb_path_ops);

-- ============================================================
-- Roles de acceso (ver brecha #2: control de acceso a auditoría)
-- ============================================================
-- Nadie debe poder modificar/borrar registros de auditoría manualmente
REVOKE UPDATE, DELETE ON audit.audit_logs FROM PUBLIC;

-- Rol de solo lectura para supervisión (Árbitro / dashboard de auditoría)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_reader') THEN
        CREATE ROLE audit_reader NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA audit TO audit_reader;
GRANT SELECT ON audit.audit_logs TO audit_reader;

-- Rol de aplicación: solo INSERT, nunca UPDATE/DELETE/TRUNCATE
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_role') THEN
        CREATE ROLE app_role NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA audit TO app_role;
GRANT INSERT, SELECT ON audit.audit_logs TO app_role;
REVOKE TRUNCATE ON audit.audit_logs FROM app_role;

-- Ningún rol de aplicación debe ser SUPERUSER ni tener BYPASSRLS
-- (verificar manualmente con \du, no se puede forzar por SQL desde aquí)
