# Auditoría — Runbook de incidentes

Procedimiento de respuesta cuando el job de verificación de integridad
(`audit_integrity_check`, cada 30 min) detecta una ruptura en la cadena
de `row_hash`/`prev_row_hash`.

## 1. Detección
El job reporta `count(*) > 0` filas donde `prev_row_hash` no coincide con
el `row_hash` esperado de la fila anterior en la misma tabla. Esto implica
una de dos cosas:
- Manipulación manual de `audit.audit_logs` (alguien con privilegios de
  owner alteró una fila).
- Corrupción de datos (poco probable, pero posible en fallos de disco).

## 2. Aislamiento inmediato
```sql
-- Identificar las filas afectadas
SELECT audit_id, table_name, created_at, row_hash, prev_row_hash
FROM audit.audit_logs
WHERE created_at > now() - interval '1 day'
  AND prev_row_hash IS DISTINCT FROM (
    SELECT row_hash FROM audit.audit_logs a2
    WHERE a2.table_name = audit.audit_logs.table_name
      AND a2.audit_id < audit.audit_logs.audit_id
    ORDER BY a2.audit_id DESC LIMIT 1
  );
```
- Revocar temporalmente accesos de escritura directa al esquema `audit`
  de cualquier rol distinto al de la aplicación (`app_role`).
- No eliminar ni modificar las filas sospechosas — son evidencia.

## 3. Investigación
- Responsable: el operador que tenga el rol de owner sobre el esquema
  `audit` (en este sistema: Capitán / administrador de Sentinel Omega).
- Revisar logs de conexión de PostgreSQL (`log_connections`,
  `log_statement = 'all'` si está habilitado) alrededor del `created_at`
  de la fila afectada.
- Cruzar con el log centralizado de Deamon-X (protocolo de logging
  obligatorio) para correlacionar la actividad del sistema en ese
  instante.

## 4. Reconciliación
- Comparar la partición sospechosa contra su copia en almacenamiento frío
  (S3/ClickHouse) exportada previamente — si la versión fría no coincide
  con la versión en caliente, se confirma manipulación posterior a la
  exportación o anterior a ella, lo que acota la ventana temporal del
  incidente.
- Si se confirma manipulación: documentar el incidente, restaurar la
  versión íntegra desde el cold storage si es necesario, y revisar/rotar
  credenciales del rol owner del esquema `audit`.

## 5. Cierre
- Registrar el incidente y su resolución en `docs/audit/` (nuevo archivo
  `incident_<fecha>.md`) para mantener trazabilidad histórica.
- Si la causa raíz fue un bug (no manipulación), corregir y agregar un
  caso de prueba de regresión.
