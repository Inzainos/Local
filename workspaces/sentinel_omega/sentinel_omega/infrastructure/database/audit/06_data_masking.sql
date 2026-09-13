-- ============================================================
-- Sentinel Omega — Auditoría: Enmascaramiento de columnas sensibles
-- (Brecha #3)
--
-- Antes de serializar OLD/NEW a JSONB, se eliminan o redactan
-- columnas configuradas como sensibles (tokens, API keys, credenciales
-- de NOAA/USGS/Copernicus, etc.) para que no queden en texto plano
-- dentro de audit.audit_logs.
-- ============================================================

-- Tabla de configuración: qué columnas redactar por tabla
CREATE TABLE IF NOT EXISTS audit.sensitive_columns (
    table_name  TEXT NOT NULL,
    column_name TEXT NOT NULL,
    PRIMARY KEY (table_name, column_name)
);

-- Ejemplos (ajustar a columnas reales del esquema):
-- INSERT INTO audit.sensitive_columns (table_name, column_name) VALUES
--     ('agentes_config', 'api_key'),
--     ('agentes_config', 'telegram_bot_token'),
--     ('credenciales_externas', 'password_hash');

CREATE OR REPLACE FUNCTION audit.fn_redact_sensitive(p_table TEXT, p_row JSONB)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_col TEXT;
    v_result JSONB := p_row;
BEGIN
    IF p_row IS NULL THEN
        RETURN NULL;
    END IF;

    FOR v_col IN
        SELECT column_name FROM audit.sensitive_columns WHERE table_name = p_table
    LOOP
        IF v_result ? v_col THEN
            v_result := jsonb_set(v_result, ARRAY[v_col], '"***REDACTED***"'::jsonb);
        END IF;
    END LOOP;

    RETURN v_result;
END;
$$;
