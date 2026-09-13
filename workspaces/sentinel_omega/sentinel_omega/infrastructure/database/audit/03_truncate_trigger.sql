-- ============================================================
-- Sentinel Omega — Auditoría: Trigger de TRUNCATE
-- TRUNCATE no dispara triggers FOR EACH ROW, requiere
-- un trigger de nivel de statement aparte (BEFORE, porque
-- después de TRUNCATE no queda rastro de las filas).
-- ============================================================

CREATE OR REPLACE FUNCTION audit.fn_audit_truncate()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO audit.audit_logs (
        user_id, db_role, schema_name, table_name, record_pk,
        operation, old_value, new_value, txid, row_hash
    ) VALUES (
        audit.fn_current_app_user(), current_user, TG_TABLE_SCHEMA, TG_TABLE_NAME,
        'ALL', 'TRUNCATE', NULL, NULL, txid_current(),
        encode(digest(TG_TABLE_NAME || 'TRUNCATE' || clock_timestamp()::TEXT, 'sha256'), 'hex')
    );
    RETURN NULL;
END;
$$;

-- Ejemplo de aplicación:
-- CREATE TRIGGER trg_audit_truncate_decisiones
--     BEFORE TRUNCATE ON public.decisiones_arbitro
--     FOR EACH STATEMENT
--     EXECUTE FUNCTION audit.fn_audit_truncate();
