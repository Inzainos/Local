# TRAIN RESTART — 2026-09-10

Timezone: America/Mexico_City (CST, UTC-6). UTC stamps labeled Z.

## Decision: NEED_TRAIN = **YES**

### Reasons
1. Dev ONNX dated 2026-09-03; Prod 2026-09-08; size divergence (delta Dev ~746KB vs old Prod ~80KB).
2. Prod **missing** `loki_unificado_rf.onnx` (Dev/Test had it).
3. Duplicate Prod path `sentinel_omega/sentinel_omega/models/`.
4. Architecture/firma work landed after some exports; explicit user request to wipe+retrain if needed.
5. Live `tbl_delta_cross` all-zeros (`data_completeness=0` for 357 rows) — poison risk for any path that reads live delta.

### Quarantine / ingest blockers (not blocking ONNX-from-firmas)
| Issue | Status | Impact on this retrain |
|---|---|---|
| `tbl_delta_cross` all zeros, completeness=0 | **QUARANTINED for training** | `train_onnx_from_db` reads **TBL_FIRMAS** only — safe |
| `tbl_delta_cross_historico` | OK (4125 rows, avg completeness ~0.77) | Not used by ONNX script; relevant for firma `--entrenar` windows |
| `tbl_schumann_vivo` stale (max ~2026-08-10), few distinct Hz | **OPEN ingest** | Not read by ONNX-from-db |
| `clima_espacial_raw` / sismos freshness | See `docs/INGEST_FIX_2026-09-10.md` (still stub/pending) | Not read by ONNX-from-db |
| Firma joint `--entrenar` (30y backcast) | **NOT re-run** this pass | Existing TBL_FIRMAS (Dev 7375) used; alfa2=18 / loki=56 → hybrid bootstrap for those bots on Dev |

**DB intact:** `SENTINEL_OMEGA_PRO.db` was never deleted.

## What was deleted (ONNX/meta only)

### Dev (`/home/deamon/workspaces-dev/sentinel_omega/models/`)
- alfa1_spaceweather_rf.onnx
- alfa2_satellite_cnn.onnx
- beta1_schumann_fft.onnx
- beta2_atmospheric_cnn.onnx
- delta_financial_lstm.onnx
- omega_espacial_rf.onnx
- loki_unificado_rf.onnx
- models_meta.json

Backup list + sha256: `docs/WEIGHTS_BACKUP_LIST_2026-09-10.md`

### Test
Mirrored from Dev after Dev train (old Test ONNX replaced). Backup note: `docs/WEIGHTS_BACKUP_LIST_TEST_2026-09-10.md` (under Test docs if written).

### Prod
Wiped `models/*.onnx` + `models_meta.json` and nested `sentinel_omega/models/*.onnx` then retrained. Backup: `docs/WEIGHTS_BACKUP_LIST_PROD_2026-09-10.md` (under Prod docs).

## Commands run

### Dev (canonical ONNX joint export)
```bash
cd /home/deamon/workspaces-dev/sentinel_omega
# Dev .venv is mis-pointed (pyvenv.cfg/pip → Prod); used workspace shared venv:
PY=/home/deamon/workspaces-dev/.venv/bin/python
export PYTHONPATH=/home/deamon/workspaces-dev
$PY models/train_onnx_from_db.py --db-path data/SENTINEL_OMEGA_PRO.db
```
- First background PID: **14809** (completed)
- Log: `docs/train_onnx_from_db_2026-09-10.log`
- Foreground stamp re-run ~18:19 CST; meta `retrained_at` **2026-09-11T00:19:25Z**

Bootstrap/`train_onnx_bootstrap.py` was **not** required as a separate pretrain step: `train_onnx_from_db` auto-hybrids bootstrap when firmas < min_samples (alfa2, loki on Dev).

`launcher.py --entrenar` (firma recognition / Juez) was **not** re-run (heavy; disk copies of ~3GB DB). ONNX refresh used existing firmas.

### Test
```bash
cp Dev/models/*.onnx Dev/models/models_meta.json → Test/models/
```

### Prod
```bash
PY=/home/deamon/workspaces/.venv/bin/python
cd /home/deamon/workspaces/sentinel_omega
$PY models/train_onnx_from_db.py --db-path data/SENTINEL_OMEGA_PRO.db
```
- PID: **17657** (completed quickly)
- Log: `docs/train_onnx_from_db_prod_2026-09-10.log`
- Prod script dated Aug 22 **lacks Loki** in BOT_DIMS → Loki ONNX **copied from Dev** into `models/` and nested `sentinel_omega/models/`.
- Full operator sheet (incl. optional systemctl): `docs/PROD_ONNX_RETRAIN_COMMANDS_2026-09-10.md`
- **No sudo / no service stop** performed.

## Post-train artifacts

### Dev / Test bots (all 7 ONNX + meta)
alfa1, alfa2, beta1, beta2, delta, omega, loki — present.

Dev sources (approx):
- db-only: alfa1(207), beta1(882), beta2(771), delta(676), omega(362)
- hybrid+bootstrap: alfa2(18+boot), loki(56+boot)

### Prod
- Retrained from Prod firmas (larger n than Dev for most bots; all db-only in log).
- **loki** present via Dev copy (Prod trainer gap).
- Nested path synced.

## TBL_PESOS_BOTS
ONNX export does **not** update `TBL_PESOS_BOTS` (still last firma/Juez timestamps). Full peso refresh requires `launcher.py --entrenar` / Juez loop — deferred.

## Follow-ups
1. Fix live delta ingest / exclude zero-completeness windows before any firma `--entrenar` that samples live `tbl_delta_cross`.
2. Upgrade Prod `models/train_onnx_from_db.py` to Dev revision (includes Loki) then re-export Loki from Prod firmas.
3. Fix Dev `.venv` (currently created with Prod path; pip installs into Prod site-packages).
4. Optional: joint `launcher.py --entrenar` once ingest blockers cleared.
5. If runtime memory-maps ONNX, restart `sentinel-omega` service (user/sudo) — not done by agent.

## Status summary
| Env | Wipe ONNX | Retrain | Loki | Notes |
|---|---|---|---|---|
| Dev | YES | YES `train_onnx_from_db` | YES | Done |
| Test | YES (via mirror) | mirrored Dev | YES | Done |
| Prod | YES | YES (older script) + Loki copy | YES (from Dev) | No sudo; service restart left to user |
