# Auditoría — Pooling de conexiones (PgBouncer)

## El problema

`SET LOCAL app.current_user_id = '<uuid>'` solo vive dentro de la transacción
actual. Si Sentinel Omega corre detrás de PgBouncer en modo `transaction` o
`statement` (necesario para soportar 5 agentes concurrentes con pocas
conexiones físicas a Postgres), la conexión física se recicla entre
transacciones de distintos clientes lógicos. Esto puede causar que
`audit.fn_current_app_user()` devuelva el UUID equivocado o el UUID "sistema"
por defecto, rompiendo la atribución de actor sin lanzar ningún error.

## Opciones de mitigación

### Opción A (recomendada si el volumen lo permite): modo `session` en PgBouncer
```ini
[pgbouncer]
pool_mode = session
```
Garantiza que cada conexión lógica de agente mantenga su propia conexión
física durante toda la sesión, preservando `SET LOCAL` de forma segura.
Costo: requiere más conexiones físicas a Postgres (una por agente activo).

### Opción B: pasar el actor como parámetro explícito (compatible con `transaction` pooling)
En vez de depender de variables de sesión, cada operación de escritura llama
a una función wrapper que recibe el `user_id` como argumento y lo setea
dentro de la misma transacción justo antes del DML:

```sql
CREATE OR REPLACE FUNCTION audit.fn_set_actor(p_user_id UUID)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM set_config('app.current_user_id', p_user_id::TEXT, true); -- true = local a la TX
END;
$$;
```

Uso desde la capa de aplicación (Python, ejemplo con `psycopg`):
```python
with conn.transaction():
    conn.execute("SELECT audit.fn_set_actor(%s)", (agente_uuid,))
    conn.execute("INSERT INTO decisiones_arbitro (...) VALUES (...)")
```

Esto funciona igual de bien con `pool_mode = transaction` porque el
`set_config(..., true)` y el DML ocurren dentro de la misma transacción,
independientemente de qué conexión física la sirva.

## Recomendación para Sentinel Omega

Dado que el orquestador (`orchestrator.py`) ya coordina los 5 agentes de
forma centralizada, usar la Opción B (función wrapper explícita) es más
robusto porque no depende de la configuración del pool — si en el futuro
cambia el modo de PgBouncer, el código de auditoría no se rompe.

## Checklist de validación

- [ ] Confirmar el `pool_mode` configurado en PgBouncer.
- [ ] Si es `transaction` o `statement`: migrar todas las llamadas de
      escritura a usar `audit.fn_set_actor()` antes de cada DML, dentro
      de la misma transacción.
- [ ] Prueba de regresión: lanzar 5 transacciones concurrentes con
      distintos `user_id` y verificar en `audit.audit_logs` que cada
      una quedó atribuida al actor correcto (no al UUID "sistema").
