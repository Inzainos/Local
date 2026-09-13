# 🤝 HANDOFF — arranque para la siguiente sesión

*Actualizado 2026-07-12 (UTC). Lee esto primero para no estrellarte.*

> **Regla #0 del proyecto (AGENTS.md / CLAUDE.md): nunca asumas, siempre
> revisa.** Verifica corriendo el flujo de punta a punta antes de decir
> "ya está". Los tests unitarios pasando NO prueban que el pipeline quede
> conectado.

## Dónde estamos
- Rama: **`claude/sentinel-omega-architecture-j3c2kn`** · PR **#83** (draft).
- Todo lo de abajo está **commiteado y empujado**. `git log --oneline` para verlo.

## Verificado de PUNTA A PUNTA (corriendo el pipeline, no solo tests)
Se sembró un mini-backcast y se corrió `entrenar()` + `barrido_diario()` +
`generar_reporte.py`. **10/10 componentes poblaron y conectaron:**
- Normalización 1NF (`tbl_firma_eventos`) + muestreo (máx 10 eventos/firma).
- Pesos (Fase 2), cimática, sesgo PRE/POST, correlaciones.
- Ruta de nodos (secuencia) con veredicto GLOBAL/LOCAL cruzando dominios.
- Cruce de precursores multi-bot: aparecieron **SOLAR, SÍSMICO, CÓSMICO,
  SCHUMANN** (los bots con datos + serie viva de Schumann).
- El reporte lee las secciones nuevas.
- (Único "hueco" investigado: el orden de precursores esconde veredictos "pocos
  casos" — correcto por diseño; con los 30 años reales sí se muestra.)

## Qué hizo esta sesión (commits de hoy)
- **Honestidad total (A–D)**: fase estricta + `viva_real`, verdad por fila con
  nodos propios, línea base de Molchan, beta1 sin numerología (Schumann MEDIDO),
  alfa1 ONNX honesto, delta sin voto ALERT, alfa2 proxy degradado.
- **Normalización + muestreo**: `eventos_json` O(n²) → tabla hija con muestra +
  conteo fiel en `recurrencia`. Índice compuesto `(bot_name, event_class)`.
- **Cimática / rutas de energía**: `tbl_cimatica_patrones` (snapshot + poda por
  eventos), `tbl_secuencia_nodos/_veredictos` (propagación global vs local),
  sobre **TODO evento natural** (sismo, volcán, tormenta solar), cruzando
  **todos los bots con datos**.
- **Schumann en vivo**: WPC de Tomsk en tiempo real cada 2h → `tbl_schumann_vivo`
  (acumula serie, no hay backcast) + LOCF si la API se corta.
- **24/7**: rutinas del vigilante (Padre 2h, Juez 4h, ejecutivo 6h, comparativo,
  semanal, mensual), correo con gráficas, tuning diario/mensual.

## PENDIENTE (lo que sigue)
1. **Correr el rebuild completo** con el código nuevo (la corrida de fondo vieja
   usa código PRE-arreglos → su resultado NO sirve, ignórala/mátala):
   ```
   nohup python deploy/rebuild_completo.py --push claude/sentinel-omega-architecture-j3c2kn \
       > estado/rebuild.log 2>&1 &
   ```
   Deja `estado/REPORTE_REBUILD.md` (pesos, sesgo PRE/POST, firmas, rutas) y lo
   empuja solo al terminar. Es de horas.
2. Decidir si **mergear los workflows de seguridad** (`apisec-scan.yml`,
   `black-duck-security-scan-ci.yml`) — **NO fueron borrados**; los creó GitHub
   Copilot en la rama `origin/copilot/clone-jupiter-branch`, nunca se mergearon
   a main ni a esta rama. Siguen ahí si se quieren.

## Gotchas (para no estrellarte)
- `sentinel_omega/data/` está en `.gitignore` — no existe en checkout limpio.
- La corrida de reentrenamiento de fondo es de **código viejo** → resultado
  superado, no lo uses. El bueno sale de `rebuild_completo.py`.
- Schumann NO tiene backcast (tabla vacía); su serie se acumula EN VIVO cada
  corrida — el dominio SCHUMANN del cruce dispara solo cuando ya hay datos.
- `entrenar_paralelo.py` (por bot) copia la DB por worker → pesado en disco;
  en contenedor acotado usar el secuencial (que ya es rápido sin el O(n²)).

## Comandos útiles (verificados)
```
python -m pytest sentinel_omega/tests/ -q          # ~410 tests
python deploy/rebuild_completo.py --push <rama>     # rebuild autónomo + reporte
python deploy/tuning_db.py --diario                 # ANALYZE (o --mensual = VACUUM)
python deploy/generar_reporte.py                    # estado/REPORTE.md
```
