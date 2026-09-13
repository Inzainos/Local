# TRAIN / INGEST VERDICT — 2026-09-10 (America/Mexico_City)

## Executive answer

| Question | Answer |
|---|---|
| ¿Hay que borrar weights y reentrenar YA? | **NO todavía.** Ingest sigue roto en Delta geo/clima/sismos. Wipe+retrain ahora **hornearía ceros / bootstrap**. |
| ¿Hace falta retrain eventualmente? | **SÍ en PROD.** Weights PROD son `bootstrap-only (2500)` del 2026-09-08 y **falta `loki_unificado_rf.onnx`**. |
| ¿DEV/TEST retrain urgente? | **No.** DEV/TEST tienen ONNX db-only/hybrid del 2026-09-03/04 (restaurados en DEV desde TEST tras wipe accidental ~18:16 CT). |
| ¿Empty Delta/Schumann envenena retrain? | **Sí el matching en vivo y features live.** ONNX retrain lee `TBL_FIRMAS` (histórico), no `tbl_delta_cross`/`tbl_schumann_vivo` directamente — pero firmas nuevas/live features con couplings=0 **sí contaminan** memoria/juez. Clima raw sin 2026 **sí afecta** `entrenamiento.py` (tormentas Kp). |

## Weight inventory

### DEV `/home/deamon/workspaces-dev/sentinel_omega/models/`
- alfa1/alfa2/beta1/beta2/delta/omega/**loki** `.onnx` presentes (copiados desde TEST 2026-09-10 18:17 CT tras borrado).
- `models_meta.json`: retrained_at **2026-09-04T00:19:15Z**, sources db-only/hybrid (NO bootstrap-only).
- Venv DEV: **roto** (imports numpy/requests fallan) — reparar antes de train en DEV.

### TEST `/home/deamon/workspaces-test/sentinel_omega/models/`
- Juego completo incl. **loki** (2026-09-03 18:19). Meta idéntica a DEV (db-only/hybrid).
- Sin `.venv` local.

### PROD `/home/deamon/workspaces/sentinel_omega/models/`
- alfa1, alfa2, beta1, beta2, delta, omega presentes (2026-09-08 12:10 CT).
- **MISSING: `loki_unificado_rf.onnx`**
- `models_meta.json`: **all bootstrap-only (2500)** — calidad inferior a DEV/TEST.
- Venv: numpy/requests/onnxruntime OK; **faltaban cv2 + yfinance** (instalados 2026-09-10).

## Root causes (ingest) — confirmed

1. **Schumann 7.83/0 forever**
   - Tomsk `http://sosrff.tsu.ru` redirige a HTTPS con **certificado expirado** → fetch falla.
   - `opencv-python` no instalado (extra `geodynamic`) → analyze devolvía baseline.
   - API devolvía fake `(7.83, 0.0)` y launcher **INSERT**aba cada hora.
2. **Delta `data_completeness=0` / couplings 0**
   - `yfinance` ausente en venv PROD → VIX/precios fallaban o degradaban.
   - `delta_enriched.fetch_schumann` (txt mensual Tomsk) también falla por SSL/404.
   - Space weather sub-fetch aún incompleto en smoke (completeness ~0.25 tras fix parcial).
3. **`tbl_clima_espacial_raw` max 2025-12-31**
   - Solo se escribe en **backcast**, no en ciclo live → hueco 2026.
4. **Sismos stalled 2026-09-03**
   - USGS API **viva** (probe OK). Writer es one-shot `topologia_cascada --refetch` (años 1994–2026), **no** está en el loop del launcher. Última corrida ~2026-09-03.

## Fixes already applied (code)

| File | Change |
|---|---|
| `infrastructure/api/schumann.py` | `verify=False` Tomsk; return `None` on fail (no fake 7.83); skip baseline placeholder |
| `infrastructure/pipeline/data_pipeline.py` | No escribe cache Schumann si `None` |
| `launcher.py` (PROD plain) | Skip INSERT `tbl_schumann_vivo` si placeholder 7.83/0 |
| `core/delta_enriched/fetchers.py` | SSL unverified para txt Tomsk |
| `infrastructure/pipeline/sismos_refetch_recent.py` | Helper incremental USGS (nuevo) |
| PROD venv | `pip install opencv-python-headless yfinance` |

Applied under: **DEV**, **TEST**, **PROD** (DEV/TEST launcher es `launcher_hex` — el skip de INSERT depende de cache `None` vía data_pipeline).

## Smoke results (PROD code + venv)

- `fetch_schumann_resonance()` → **`(8.26, 21.46)`** (REAL, no placeholder)
- `fetch_all(days=7)` → prices=True, space=False, schumann_txt=False, completeness≈**0.25**
- USGS feed OK; sismos DB aún sin refetch ejecutado

## Do-not-wipe gate

```
IF schumann real AND delta completeness > 0.5 AND clima has 2026 rows AND sismos max within 24h
THEN wipe PROD bootstrap onnx + copy/retrain from DEV firmas (DEV first)
ELSE keep fixing ingest
```

## Smallest safe next steps (ordered)

1. Reparar **DEV venv** (`pip install -e ".[geodynamic,bolsa,dashboard]"` o recrear).
2. Arreglar `fetch_space_weather` en `delta_enriched/fetchers.py` (NOAA) hasta completeness ≥0.5.
3. Writer live incremental → `tbl_clima_espacial_raw` desde alfa1 OMNI (o backcast gap-fill 2026 YTD).
4. Correr `sismos_refetch_recent.py --db PROD --days 14` (sin entrenar).
5. Reiniciar servicio Sentinel (**usuario**, sin sudo desde agente):
   `systemctl --user restart sentinel-omega.service`  (hoy MainPID=0 / inactive)
6. Solo entonces: borrar PROD `*.onnx` bootstrap, copiar loki desde TEST/DEV, `train_onnx_from_db` en DEV → promover a TEST → PROD.

## Restart command (for user)

```bash
wsl -d kali-linux -- bash -lc 'systemctl --user restart sentinel-omega.service; systemctl --user status sentinel-omega.service --no-pager'
```

Si el unit no existe / inactive: usar el launcher habitual del entorno (documentar PID tras arranque). No sudo.
