-- ============================================================
-- Sentinel Omega — Auditoría: Auto-instrumentación de tablas nuevas
-- (Brecha #4 — prioridad alta)
--
-- Un event trigger DDL detecta CREATE TABLE en el esquema public
-- y aplica automáticamente el trigger de auditoría, para que
-- ninguna tabla nueva del sistema quede sin auditar por descuido.
-- ============================================================

CREATE OR REPLACE FUNCTION audit.fn_auto_instrument_new_table()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    obj record;
    v_schema TEXT;
    v_table  TEXT;
BEGIN
    FOR obj IN SELECT * FROM pg_event_trigger_ddl_commands()
    LOOP
        IF obj.command_tag = 'CREATE TABLE' AND obj.schema_name = 'public' THEN
            v_schema := obj.schema_name;
            v_table  := split_part(obj.object_identity, '.', 2);

            -- Evitar instrumentar tablas que empiecen con "tmp_" o "staging_"
            IF v_table LIKE 'tmp\_%' OR v_table LIKE 'staging\_%' THEN
                CONTINUE;
            END IF;

            EXECUTE format(
                'CREATE TRIGGER trg_audit_%s
                 AFTER INSERT OR UPDATE OR DELETE ON %I.%I
                 FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_trigger()',
                v_table, v_schema, v_table
            );
            EXECUTE format(
                'ALTER TABLE %I.%I ENABLE ALWAYS TRIGGER trg_audit_%s',
                v_schema, v_table, v_table
            );
            EXECUTE format(
                'CREATE TRIGGER trg_audit_truncate_%s
                 BEFORE TRUNCATE ON %I.%I
                 FOR EACH STATEMENT EXECUTE FUNCTION audit.fn_audit_truncate()',
                v_table, v_schema, v_table
            );

            RAISE NOTICE 'Auditoría auto-instrumentada en tabla %.%', v_schema, v_table;
        END IF;
    END LOOP;
END;
$$;

CREATE EVENT TRIGGER trg_auto_audit_new_tables
    ON ddl_command_end
    WHEN TAG IN ('CREATE TABLE')
    EXECUTE FUNCTION audit.fn_auto_instrument_new_table();

-- Para revertir en caso de necesitar crear una tabla sin auditoría:
-- ALTER EVENT TRIGGER trg_auto_audit_new_tables DISABLE;
-- ... CREATE TABLE ...
-- ALTER EVENT TRIGGER trg_auto_audit_new_tables ENABLE;
