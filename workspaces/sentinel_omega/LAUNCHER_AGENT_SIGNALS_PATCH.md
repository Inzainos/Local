# Parche launcher — agent_signals + ventana adaptativa

El módulo ya está en main:

`sentinel_omega/infrastructure/pipeline/juez_cycle_register.py`

## Cambio en `launcher.py`

Busca el bloque que registra solo al Padre con `ventana_h=72` y **sustitúyelo** por:

```python
        from sentinel_omega.infrastructure.pipeline.juez_cycle_register import (
            register_cycle_predictions,
        )
        register_cycle_predictions(
            juez, geo, matches=matches, conn=conn,
            muro_lags=muro_lags, nodos_pred=nodos_pred,
        )
```

### Qué hace
- `ventana_h` dinámica: mínimo 2h, lag de firma / `tbl_lag_anticipacion`, tope 90 días
- `registrar_prediccion` para **padre** y para **cada bot** en `geo.agent_signals`
- El Juez puede castigar/reforzar a todos los que alertaron (no solo Padre)

### Alternativa (tar)
```bash
tar xzf sentinel_omega_COMPLETO_sesion.tar.gz
# trae launcher completo ya cableado
```
