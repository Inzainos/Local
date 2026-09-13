# Restaurar schema.py completo (SCHEMA_VERSION 11)

El archivo `sentinel_omega/infrastructure/database/schema.py` en `main` puede quedar
como stub por límites del conector de push. **Fuente de verdad**:

```bash
# Desde la raíz del repo workspaces
tar xzf path/to/sentinel_omega_COMPLETO_sesion.tar.gz
# o
tar xzf path/to/sentinel_omega_github_push.tar.gz

# Verificar
grep -n "SCHEMA_VERSION = 11\|tbl_locf_cache\|tbl_eventos_catalogo" \
  sentinel_omega/infrastructure/database/schema.py

git add sentinel_omega/infrastructure/database/schema.py
git add -A   # resto del paquete
git commit -m "feat(sentinel): restore full schema v11 + session package"
git push origin main
```

El tar `sentinel_omega_COMPLETO_sesion.tar.gz` incluye el paquete íntegro de la sesión
(LOCF, ONNX+Omega, Juez 2h, dual-ask, Telegram Centinela V2, lags, dashboard, etc.).

## Ya en main (sesión de push parcial)
- Telegram Centinela V2 (`infrastructure/api/telegram.py`)
- Padre dual-ask + Omega referencia (`layers/geodynamic/padre/agent.py`)
- `SESSION_FIXES_COMPLETO.md`
- ONNX mixin/config, train_onnx_*, layer_runners, verificacion, omega agent,
  orchestrator, requirements, deploy services (commits previos)

## Acción recomendada
Extraer el tar completo y hacer **un solo commit** con el árbol íntegro para
evitar desalineación archivo-a-archivo.
