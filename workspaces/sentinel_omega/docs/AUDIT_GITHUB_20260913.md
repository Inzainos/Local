# Auditoría GitHub Inzainos/Local — 2026-09-13

Rama: `local/sentinel-omega` (también aplica contexto a `local/watchdog`).
Origen: revisión Claude/Copilot + inventario Agente-C. **Cero secretos** detectados en el push.

## Hallazgos (H1–H6)

| ID | Severidad | Hallazgo | Evidencia | Remediación propuesta | Estado |
|----|-----------|----------|-----------|----------------------|--------|
| H1 | Med | Workflows GitHub Actions en el tree | `workspaces/.github/workflows/`: bandit, codeql, copy-delta-to-snt, roy-vigilante | Decidir: Actions→`main` / `workflow_dispatch` / solo systemd local | **Pendiente GO Capitán** |
| H2 | Med | Modelos ONNX duplicados (anidados) | Canónico: `workspaces/sentinel_omega/models/*.onnx`. Anidados: `workspaces/sentinel_omega/sentinel_omega/models/*.onnx` | Mantener solo primer nivel; borrar anidados del git | **Hecho** en `b639aa8` (archivados en `_archive/20260913/models_nested/`; `loki` borrado por blob idéntico) |
| H3 | Med | Backups/artefactos `.bak*` en git | p.ej. `*.bak_20260910`, `*.bak_ingest_*`, `launcher_hex_backup_*`, `_SCHEMA_PARTS_BACKUP_PRE_FIX.tar.gz` | Quitar del índice + gitignore `*.bak*` / `*_backup_*` | **Hecho.** `b639aa8` sacó 40 archivos; el relevo archivó los 2 que el glob no alcanzó (`launcher_fixed.py`, `launcher.py.broken-2026-09-10`) |
| H4 | Med | Symlinks frágiles | (1) `workspaces/.agents/skills/developing-with-streamlit` → `.venv/.../streamlit/...` (rompe sin venv). (2) `sentinel_omega/sentinel_omega/data` → `../data` | Quitar symlink al venv; documentar o normalizar `data` | **Hecho** en esta rama (`b639aa8`); `data` se conserva y queda documentado. Los dos análogos de `local/padron` los cubre el relevo |
| H5 | — | (no asignado a C en esta pasada / secrets) | Push sin `.env`; gitignore cubre `.env` | Mantener | OK |
| H6 | Low/Med | Retención `estado/` | ~1117 archivos bajo `workspaces/estado/` | Política de retención (p.ej. últimos N días) o sacar reportes generados del repo | **Pendiente GO Capitán** |

## `local/watchdog`

Tree limpio de `.venv` / `.bak` en origin. Sin remediación H2/H3/H4 análoga.

## Decisiones humanas (no tocar sin GO)

1. **Actions:** ¿habilitar sobre `main`, solo `workflow_dispatch`, o confiar en systemd Kali?
2. **Models anidados + baks:** ¿borrar del repo en un commit de limpieza?
3. **Licencia:** MIT vs Proprietary (monorepo / subproyectos) → coordinación G.
4. **Retención `estado/`:** ¿cuántos días / exclusiones?

## Notas ops relacionadas (mismo día, no son hallazgos del push)

- Schumann vivo refrescado 2026-09-13 21:00 (8.26/21.46).
- Harden: `.env` mode 600; dashboard `:8510` → 127.0.0.1; mantenimiento `--dry-run` drop-in.
- FK orphans limpiados: `FK_CHECK=0`; archives `TBL_*_orphans_20260913_153039`.

## Owners

- Agente-C: `local/sentinel-omega`, `local/watchdog`
- Agente-T: `local/concilio`
- Agente-A: `local/home-bridge`, `local/deamonx-bridge-v1.0.0`
- **Sin asignar: `local/padron`** — cubierto por el relevo en esta pasada.

---

## Incidente `/data` (2026-09-13, lado máquina)

El glob `*.bak*` aplicado sobre el árbol vivo también alcanzó copias
`data/*.db.bak*`, que nunca estuvieron versionadas. DB canónica verificada
(`integrity_check=ok`). Snapshot vigente:
`data/backups/SENTINEL_OMEGA_PRO.db.copy-20260913_post_classify` (873 MB).

**Riesgo residual:** con un solo snapshot no hay historia de restauración. Las
copias perdidas eran los puntos de retorno anteriores a hoy.

**Regla:** nunca aplicar globs de limpieza sobre `data/`. Y como la regla depende
de que cada agente la recuerde, la mitigación estructural es sacar los respaldos
de DB fuera del árbol del proyecto — hoy `data/backups/` vive dentro del mismo
directorio que se limpia. Patrón ya probado en casa:
`watchdog/scripts/offbox_backup.sh` (copia off-box con retención de 30 días).

## Nota de encoding

La primera versión de este documento se escribió en ASCII y perdió 36
caracteres no-ASCII (acentos y rayas quedaron como `?`). Restaurados en UTF-8
sin cambiar el contenido. La causa está en el pipeline de escritura de
Agente-C, no en el archivo; el mensaje del commit `30c9b64` conserva la
mutilación original porque la historia no se reescribe.
