# Auditor?a GitHub Inzainos/Local ? 2026-09-13

Rama: `local/sentinel-omega` (tambi?n aplica contexto a `local/watchdog`).
Origen: revisi?n Claude/Copilot + inventario Agente-C. **Cero secretos** detectados en el push.

## Hallazgos (H1?H6)

| ID | Severidad | Hallazgo | Evidencia | Remediaci?n propuesta | Estado |
|----|-----------|----------|-----------|----------------------|--------|
| H1 | Med | Workflows GitHub Actions en el tree | `workspaces/.github/workflows/`: bandit, codeql, copy-delta-to-snt, roy-vigilante | Decidir: Actions?`main` / `workflow_dispatch` / solo systemd local | **Pendiente GO Capit?n** |
| H2 | Med | Modelos ONNX duplicados (anidados) | Can?nico: `workspaces/sentinel_omega/models/*.onnx`. Anidados: `workspaces/sentinel_omega/sentinel_omega/models/*.onnx` | Mantener solo primer nivel; borrar anidados del git | **Pendiente GO** |
| H3 | Med | Backups/artefactos `.bak*` en git | p.ej. `*.bak_20260910`, `*.bak_ingest_*`, `launcher_hex_backup_*`, `_SCHEMA_PARTS_BACKUP_PRE_FIX.tar.gz` | Quitar del ?ndice + gitignore `*.bak*` / `*_backup_*` | **Pendiente GO** |
| H4 | Med | Symlinks fr?giles | (1) `workspaces/.agents/skills/developing-with-streamlit` ? `.venv/.../streamlit/...` (rompe sin venv). (2) `sentinel_omega/sentinel_omega/data` ? `../data` | Quitar symlink al venv; documentar o normalizar `data` | **Pendiente GO** (venv); data OK documentar |
| H5 | ? | (no asignado a C en esta pasada / secrets) | Push sin `.env`; gitignore cubre `.env` | Mantener | OK |
| H6 | Low/Med | Retenci?n `estado/` | ~1117 archivos bajo `workspaces/estado/` | Pol?tica de retenci?n (p.ej. ?ltimos N d?as) o sacar reportes generados del repo | **Pendiente GO Capit?n** |

## `local/watchdog`

Tree limpio de `.venv` / `.bak` en origin. Sin remediaci?n H2/H3/H4 an?loga.

## Decisiones humanas (no tocar sin GO)

1. **Actions:** ?habilitar sobre `main`, solo `workflow_dispatch`, o confiar en systemd Kali?
2. **Models anidados + baks:** ?borrar del repo en un commit de limpieza?
3. **Licencia:** MIT vs Proprietary (monorepo / subproyectos) ? coordinaci?n G.
4. **Retenci?n `estado/`:** ?cu?ntos d?as / exclusiones?

## Notas ops relacionadas (mismo d?a, no son hallazgos del push)

- Schumann vivo refres?ado 2026-09-13 21:00 (8.26/21.46).
- Harden: `.env` mode 600; dashboard `:8510` ? 127.0.0.1; mantenimiento `--dry-run` drop-in.
- FK orphans limpiados: `FK_CHECK=0`; archives `TBL_*_orphans_20260913_153039`.

## Owners

- Agente-C: `local/sentinel-omega`, `local/watchdog`
- Agente-T: `local/concilio`
- Agente-A: `local/home-bridge`, `local/deamonx-bridge-v1.0.0`
