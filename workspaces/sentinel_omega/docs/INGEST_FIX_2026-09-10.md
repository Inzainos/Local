# Ingest Fix — 2026-09-10

Estado: **DONE** (code shipped DEV → TEST → PROD + nested).  
Documentado: 2026-09-10 18:34 CT (America/Mexico_City)

## Symptoms (before)

| Table | Symptom |
|---|---|
| `tbl_delta_cross` | Hourly rows with all couplings 0, `data_completeness=0.0`, fake `EQUILIBRIUM` / conf≈0.15 |
| `tbl_schumann_vivo` | Always `hz=7.83`, `activity=0` (baseline written as live) |
| `tbl_clima_espacial_raw` | No 2026 rows (max 2025-12-31) |
| `tbl_eventos_sismicos_fuente` | Stalled ~2026-09-03 |

## Root causes

1. **Schumann placeholder poison**
   - Tomsk `sosrff.tsu.ru` HTTP→HTTPS with **expired TLS cert** → download failed.
   - `opencv` missing historically → analyze returned fake `(7.83, 0.0)`.
   - Callers INSERT’d baseline every hour as if live.
   - Tomsk monthly **TXT feed is 404** (confirmed 2026-09-10) — only spectrogram JPG remains.

2. **Delta `fetch_space_weather` returned None**
   - NOAA timestamps lack `Z` → naive vs aware UTC compare raised `TypeError`, silently skipped **all** rows.
   - IMF **Bz** lives on `rtsw_mag_1m.json`, not wind JSON (code looked in wind).
   - Proton JSON is `list[dict]` (`flux`/`energy`), not `[ts, val]` pairs.

3. **Delta writer**
   - `data_pipeline._persist_delta` INSERT’d even when completeness=0 / couplings all None/0.
   - Composite labeled `EQUILIBRIUM` with non-zero confidence on incomplete data.

4. **Clima raw**
   - Live loop did not write `tbl_clima_espacial_raw` (backcast-only historically).

5. **Sismos**
   - USGS writer is one-shot (`--refetch` / incremental helper), not launcher loop. Stale until manual run.

## Files changed

Patched in **DEV** then copied to **TEST**, **PROD**, and **PROD nested** `sentinel_omega/sentinel_omega/`:

| Rel path | Change |
|---|---|
| `core/delta_enriched/fetchers.py` | UTC-aware NOAA parse; MAG Bz; proton dict; Schumann TXT→WPC→DB LOCF; (attempt 7-day products — currently 404) |
| `core/delta_enriched/composite.py` | `NO_DATA` / `INCOMPLETE` instead of fake `EQUILIBRIUM` when completeness low |
| `core/delta_enriched/historico.py` | Same honesty for historico composite |
| `infrastructure/pipeline/data_pipeline.py` | Schumann None skip; **refuse junk** `tbl_delta_cross` INSERT; safe log |
| `infrastructure/database/repository.py` | Stronger `insert_delta_cross` junk guard + INCOMPLETE remap |
| `infrastructure/api/schumann.py` | `verify=False` Tomsk; return `None` on fail; no fake 7.83/0 (prior partial fix kept) |
| `infrastructure/pipeline/clima_gapfill_2026.py` | One-shot NOAA→`tbl_clima_espacial_raw` (helper) |
| `infrastructure/pipeline/sismos_refetch_recent.py` | Incremental USGS upsert helper |
| `launcher.py` (PROD) | Skip `tbl_schumann_vivo` INSERT of placeholder 7.83/0 (prior partial fix) |

Backups: `*.bak_ingest_<stamp>` / earlier `*.bak_20260910` alongside originals.

## Smoke results (PROD venv, PYTHONPATH=workspaces)

```
schumann_resonance → (8.26, 21.46)   # REAL, not placeholder
fetch_prices(7)    → OK (13 tickers)
fetch_space_weather→ OK (kp/bz/wind/proton finite; ~2 recent days from 1m feeds)
fetch_schumann     → OK via WPC fallback (TXT 404)
fetch_all          → prices=True space=True schumann=True trends=False
run_composite      → completeness=0.75 regime=SCHUMANN_SHIFT conf≈0.40
```

Trends require `pytrends` (optional; not installed in PROD venv).

## SQL samples (PROD `data/SENTINEL_OMEGA_PRO.db`)

### Before (junk / stall — representative)

```sql
-- delta: completeness 0 + EQUILIBRIUM
SELECT timestamp_blk, cross_coupling, data_completeness, regime_label, confidence
FROM tbl_delta_cross ORDER BY timestamp_blk DESC LIMIT 3;
-- 2026-09-11 00:00:00 | 0.0 | 0.0 | EQUILIBRIUM | 0.15

-- schumann: baseline forever
SELECT timestamp_blk, schumann_hz, schumann_activity
FROM tbl_schumann_vivo ORDER BY timestamp_blk DESC LIMIT 3;
-- … 7.83 / 0.0 …

-- clima: no 2026 (historical report)
-- SELECT MAX(timestamp_blk) → 2025-12-31

-- sismos: stalled ~2026-09-03
```

### After (post-fix / one-shots)

```sql
-- schumann live row (real WPC)
-- 2026-09-11 00:00 | 8.26 | 21.46

-- clima 2026 present (SWPC hourly gap-fill; live window ~25 hours)
SELECT MAX(timestamp_blk), COUNT(*),
       SUM(CASE WHEN timestamp_blk LIKE '2026%' THEN 1 ELSE 0 END)
FROM tbl_clima_espacial_raw;
-- max=2026-09-11 00:00 | n≈280377 | n2026=25

SELECT timestamp_blk, bz_promedio, kp_max, viento_solar_avg
FROM tbl_clima_espacial_raw WHERE timestamp_blk LIKE '2026%'
ORDER BY timestamp_blk DESC LIMIT 3;
-- 2026-09-11 00:00 | ~0.86 | 0.0 | ~440
-- 2026-09-10 23:00 | ~1.25 | 3.0 | ~443

-- sismos refreshed
SELECT MAX(time_utc), COUNT(*) FROM tbl_eventos_sismicos_fuente;
-- max=2026-09-10 23:03:42 | n≈213631

-- delta: old junk rows remain until next honest cycle;
-- writer now SKIPS completeness==0 / all-zero coupling junk.
```

## One-shot commands (safe, no wipe)

```bash
wsl -d kali-linux -- bash -lc '
  PY=/home/deamon/workspaces/sentinel_omega/.venv/bin/python
  ROOT=/home/deamon/workspaces/sentinel_omega
  DB=$ROOT/data/SENTINEL_OMEGA_PRO.db
  export PYTHONPATH=$ROOT
  $PY $ROOT/infrastructure/pipeline/clima_gapfill_2026.py --db "$DB"
  $PY $ROOT/infrastructure/pipeline/sismos_refetch_recent.py --db "$DB" --days 14
'
```

Full USGS multi-year refetch (optional, slow):

```bash
$PY $ROOT/infrastructure/pipeline/topologia_cascada.py --db-path "$DB" --refetch
```

## Restart needed?

**YES — user should restart prod launcher** so running process loads patched modules (and clears any LOCF cache holding old 7.83/0).

Prefer user-level (no password sudo hang):

```bash
wsl -d kali-linux -- bash -lc 'systemctl --user restart sentinel-omega.service; systemctl --user status sentinel-omega.service --no-pager'
```

If unit is system-wide / inactive, use the site’s usual launcher restart.  
Documented alternative mentioned by ops: `sudo systemctl restart sentinel-omega` (may prompt password — do **not** run from unattended agent).

After restart, expect:
- New `tbl_schumann_vivo` rows ≠ 7.83/0 when Tomsk JPG reachable
- New `tbl_delta_cross` rows only when completeness > 0 (or honest INCOMPLETE), not hourly zero junk

## Remaining / follow-ups

1. **Clima YTD gap (Jan–Aug 2026)** — SWPC 1m feeds only cover ~1 day; full OMNI/backcast gap-fill still needed for training-grade 2026 history (`n2026` currently ≈25 hourly buckets).
2. **Cross couplings may stay ~0** until multi-day aligned series accumulate (WPC schumann is 1-point; space wx ~2 days). Completeness 0.75 is already enough to stop NO_DATA poisoning.
3. Optional: `pip install pytrends` in PROD venv for trends leg (4th source → completeness 1.0).
4. Do **not** wipe/retrain ONNX until ingest gate stays green (see `docs/TRAIN_INGEST_VERDICT_2026-09-10.md`).

## Explicitly out of scope (this fix)

- `--entrenar` / firmas / remapeo
- Destructive DB wipe
- Password `sudo` from agent
