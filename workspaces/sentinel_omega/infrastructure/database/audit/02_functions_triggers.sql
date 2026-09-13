-- ============================================================
-- Sentinel Omega — Auditoría: Funciones y triggers (DML)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- requerido por digest()

-- ============================================================
-- Resuelve el usuario lógico de la sesión (agente: Alfa/Beta/Delta/Árbitro)
-- La app debe ejecutar al abrir cada transacción:
--   SET LOCAL app.current_user_id = '<uuid>';
-- Ver 05_pgbouncer_pooling.sql para la limitación con pooling de conexiones.
-- ============================================================
CREATE OR REPLACE FUNCTION audit.fn_current_app_user()
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_user TEXT;
BEGIN
    v_user := current_setting('app.current_user_id', true);
    IF v_user IS NULL OR v_user = '' THEN
        RETURN '00000000-0000-0000-0000-000000000000'::UUID;
    END IF;
    RETURN v_user::UUID;
EXCEPTION WHEN OTHERS THEN
    RETURN '00000000-0000-0000-0000-000000000000'::UUID;
END;
$$;

-- ============================================================
-- Función principal de auditoría (AFTER ROW trigger)
-- Captura INSERT, UPDATE, DELETE. Excluye columnas sensibles
-- vía audit.fn_redact_sensitive() (ver 07_data_masking.sql).
-- ============================================================
CREATE OR REPLACE FUNCTION audit.fn_audit_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = audit, pg_temp
AS $$
DECLARE
    v_old JSONB;
    v_new JSONB;
    v_pk  TEXT;
    v_changed TEXT[];
    v_last_hash TEXT;
    v_row_hash TEXT;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_old := NULL;
        v_new := audit.fn_redact_sensitive(TG_TABLE_NAME, to_jsonb(NEW));
        v_pk  := (to_jsonb(NEW)->>'id');
    ELSIF TG_OP = 'UPDATE' THEN
        v_old := audit.fn_redact_sensitive(TG_TABLE_NAME, to_jsonb(OLD));
        v_new := audit.fn_redact_sensitive(TG_TABLE_NAME, to_jsonb(NEW));
        v_pk  := (to_jsonb(NEW)->>'id');
        SELECT array_agg(key) INTO v_changed
        FROM jsonb_each(to_jsonb(NEW)) n
        WHERE n.value IS DISTINCT FROM (to_jsonb(OLD) -> n.key);
    ELSIF TG_OP = 'DELETE' THEN
        v_old := audit.fn_redact_sensitive(TG_TABLE_NAME, to_jsonb(OLD));
        v_new := NULL;
        v_pk  := (to_jsonb(OLD)->>'id');
    END IF;

    SELECT row_hash INTO v_last_hash
    FROM audit.audit_logs
    WHERE table_name = TG_TABLE_NAME
    ORDER BY audit_id DESC
    LIMIT 1;

    v_row_hash := encode(
        digest(
            coalesce(v_last_hash, '') ||
            TG_TABLE_NAME || v_pk || TG_OP ||
            coalesce(v_old::TEXT, '') || coalesce(v_new::TEXT, '') ||
            clock_timestamp()::TEXT,
            'sha256'
        ),
        'hex'
    );

    INSERT INTO audit.audit_logs (
        user_id, db_role, application_name, client_addr,
        schema_name, table_name, record_pk, operation,
        old_value, new_value, changed_fields,
        txid, row_hash, prev_row_hash
    ) VALUES (
        audit.fn_current_app_user(), current_user, current_setting('application_name', true),
        inet_client_addr(),
        TG_TABLE_SCHEMA, TG_TABLE_NAME, v_pk, TG_OP::audit.operation_type,
        v_old, v_new, v_changed,
        txid_current(), v_row_hash, v_last_hash
    );

    RETURN COALESCE(NEW, OLD);
END;
$$;

-- ============================================================
-- Ejemplo de aplicación sobre una tabla crítica
-- (ajustar el nombre de tabla a las tablas reales de Sentinel Omega,
--  p.ej. tbl_ciclos, tbl_detecciones, tbl_muro_eventos)
-- ============================================================
-- CREATE TRIGGER trg_audit_decisiones_arbitro
--     AFTER INSERT OR UPDATE OR DELETE ON public.decisiones_arbitro
--     FOR EACH ROW
--     EXECUTE FUNCTION audit.fn_audit_trigger();
--
-- ALTER TABLE public.decisiones_arbitro
--     ENABLE ALWAYS TRIGGER trg_audit_decisiones_arbitro;
