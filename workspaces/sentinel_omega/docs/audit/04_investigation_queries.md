# Auditoría — Consultas de investigación

Queries listas para usar sobre `audit.audit_logs`, aprovechando los
índices definidos en `infrastructure/database/audit/01_schema.sql`.

## ¿Quién modificó el registro X entre dos fechas?
```sql
SELECT user_id, db_role, operation, old_value, new_value, created_at
FROM audit.audit_logs
WHERE table_name = 'decisiones_arbitro'
  AND record_pk = '42'
  AND created_at BETWEEN '2026-06-01' AND '2026-06-30'
ORDER BY created_at;
```

## Historial completo de cambios de un usuario/agente
```sql
SELECT table_name, record_pk, operation, changed_fields, created_at
FROM audit.audit_logs
WHERE user_id = '3f29...-uuid-del-agente'
ORDER BY created_at DESC
LIMIT 200;
```

## Todas las operaciones sobre una tabla en las últimas 6 horas
(útil para correlacionar con los bloques de 6h de Sentinel Omega)
```sql
SELECT operation, count(*)
FROM audit.audit_logs
WHERE table_name = 'tbl_ciclos'
  AND created_at > now() - interval '6 hours'
GROUP BY operation;
```

## Buscar un valor específico dentro del JSON (usa índice GIN)
```sql
SELECT audit_id, table_name, record_pk, created_at
FROM audit.audit_logs
WHERE new_value @> '{"nivel_riesgo": "HIGH"}'::jsonb
ORDER BY created_at DESC;
```

## Reconstrucción del valor en un punto en el tiempo
```sql
SELECT new_value
FROM audit.audit_logs
WHERE table_name = 'tbl_nodos_topologia'
  AND record_pk = '17'
  AND created_at <= '2026-06-15 12:00:00'
ORDER BY created_at DESC
LIMIT 1;
```

## Detectar transacciones que tocaron múltiples tablas (posible acción compuesta del Árbitro)
```sql
SELECT txid, array_agg(DISTINCT table_name) AS tablas_afectadas, count(*) AS filas
FROM audit.audit_logs
WHERE created_at > now() - interval '1 day'
GROUP BY txid
HAVING count(DISTINCT table_name) > 1;
```
