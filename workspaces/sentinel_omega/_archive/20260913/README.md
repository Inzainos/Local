# Archive 2026-09-13 (Agente-C)

- `models_nested/`: ONNX from `sentinel_omega/sentinel_omega/models/` (sha differed from canonical `sentinel_omega/models/`). Canonical path remains active.
- `schema/`: schema_parts backup tarballs moved out of active tree.
- Deleted obsolete: `*.bak*`, `launcher_hex_backup_*`, venv→streamlit symlink.

## Añadido después (relevo de Agente-C, sin créditos)

- `launchers/`: dos variantes del launcher que el glob `*.bak*` no alcanzó porque
  su nombre no casa con ese patrón. Ninguna es duplicado del vigente:

  | Archivo | Bytes | Qué es |
  |---|---|---|
  | `launcher_fixed.py` | 38 999 | Variante; el vigente `launcher.py` tiene 39 441 |
  | `launcher.py.broken-2026-09-10` | 31 566 | Versión rota del 2026-09-10, conservada por referencia |

  Se archivan en vez de borrarse por el mismo criterio que los ONNX anidados:
  contenido distinto del canónico, así que no se descarta sin decisión humana.
  El launcher vigente sigue siendo `sentinel_omega/launcher.py`, auto-expandible
  desde `launcher_hex/`.

## Cómo recuperar cualquier cosa de aquí

```bash
git mv workspaces/sentinel_omega/_archive/20260913/<ruta> workspaces/sentinel_omega/<destino>
```

Y lo que sí se borró (los `*.bak*`, `launcher_hex_backup_*` y el symlink al venv)
sigue en la historia, recuperable con:

```bash
git checkout b639aa8^ -- <ruta>
```
