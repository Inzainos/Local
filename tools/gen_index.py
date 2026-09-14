#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generador del indice de sistemas locales (repo Inzainos/Local).

Lee las ramas reales del remoto, las clasifica y regenera la seccion
auto-gestionada del README (tabla de sistemas + ramas de revision + comandos
de clonado) entre los marcadores AUTO-INDEX. La prosa escrita a mano fuera de
los marcadores nunca se toca.

Clasificacion de ramas:
  - local/*            -> sistema (va en la tabla principal)
  - review/* , wip/*   -> rama de revision / efimera (lista aparte)
  - main, claude/*     -> infraestructura (se ignora en el indice)

Uso:
  python3 tools/gen_index.py            # regenera README.md en el sitio
  python3 tools/gen_index.py --check    # NO escribe; sale 1 si esta desfasado
  python3 tools/gen_index.py --remote origin --readme README.md

Todos los logs quedan en logs/gen_index.log y en consola.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

# --- Rutas por defecto (relativas a la raiz del repo) -----------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_README = REPO_ROOT / "README.md"
DEFAULT_METADATA = REPO_ROOT / "tools" / "systems.json"
DEFAULT_LOG_DIR = REPO_ROOT / "logs"

# --- Marcadores de la seccion auto-gestionada del README --------------------
BEGIN_MARKER = "<!-- BEGIN:AUTO-INDEX -->"
END_MARKER = "<!-- END:AUTO-INDEX -->"

# --- Prefijos de clasificacion ----------------------------------------------
SYSTEM_PREFIX = "local/"
REVIEW_PREFIXES = ("review/", "wip/")
INFRA_PREFIXES = ("claude/",)
INFRA_EXACT = {"main", "HEAD"}

LOG = logging.getLogger("gen_index")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(log_dir: Path) -> Path:
    """Configura logging a consola + archivo. Devuelve la ruta del log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "gen_index.log"

    LOG.setLevel(logging.DEBUG)
    LOG.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%dT%H:%M:%S%z"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    LOG.addHandler(console)

    fileh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    fileh.setLevel(logging.DEBUG)
    fileh.setFormatter(fmt)
    LOG.addHandler(fileh)

    return log_file


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------
def list_remote_branches(remote: str) -> list[tuple[str, str]]:
    """Devuelve [(branch, short_sha)] del remoto, ordenado por nombre de rama.

    Usa `git ls-remote --heads` para no depender de fetch previo.
    """
    cmd = ["git", "ls-remote", "--heads", remote]
    LOG.debug("Ejecutando: %s", " ".join(cmd))
    try:
        out = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError:
        LOG.error("git no esta disponible en el PATH.")
        raise
    except subprocess.CalledProcessError as exc:
        LOG.error("git ls-remote fallo (%s): %s", exc.returncode, exc.stderr.strip())
        raise

    branches: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/heads/"):
            continue
        branch = ref[len("refs/heads/") :]
        branches.append((branch, sha[:7]))

    branches.sort(key=lambda b: b[0])
    LOG.info("Ramas remotas encontradas: %d", len(branches))
    for name, sha in branches:
        LOG.debug("  %s  %s", sha, name)
    return branches


# ---------------------------------------------------------------------------
# Clasificacion
# ---------------------------------------------------------------------------
def classify(branches: list[tuple[str, str]]) -> dict[str, list[tuple[str, str]]]:
    """Reparte las ramas en systems / review / infra segun su prefijo."""
    buckets: dict[str, list[tuple[str, str]]] = {
        "systems": [],
        "review": [],
        "infra": [],
    }
    for name, sha in branches:
        if name in INFRA_EXACT or name.startswith(INFRA_PREFIXES):
            buckets["infra"].append((name, sha))
        elif name.startswith(SYSTEM_PREFIX):
            buckets["systems"].append((name, sha))
        elif name.startswith(REVIEW_PREFIXES):
            buckets["review"].append((name, sha))
        else:
            # Desconocida: la tratamos como infra pero la avisamos.
            LOG.warning("Rama sin clasificar (tratada como infra): %s", name)
            buckets["infra"].append((name, sha))

    LOG.info(
        "Clasificacion -> sistemas: %d | revision: %d | infra: %d",
        len(buckets["systems"]),
        len(buckets["review"]),
        len(buckets["infra"]),
    )
    return buckets


# ---------------------------------------------------------------------------
# Metadatos
# ---------------------------------------------------------------------------
def load_metadata(path: Path) -> dict[str, dict[str, str]]:
    """Carga systems.json (descripciones curadas por rama)."""
    if not path.exists():
        LOG.warning("No existe %s; se usaran descripciones pendientes.", path)
        return {}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    meta = {k: v for k, v in data.items() if not k.startswith("_")}
    LOG.info("Metadatos cargados para %d ramas.", len(meta))
    return meta


# ---------------------------------------------------------------------------
# Render markdown
# ---------------------------------------------------------------------------
def render_block(
    buckets: dict[str, list[tuple[str, str]]],
    metadata: dict[str, dict[str, str]],
    remote_url: str,
) -> str:
    """Construye el bloque markdown auto-gestionado (sin los marcadores)."""
    lines: list[str] = []

    lines.append(
        "> Tabla generada automaticamente por `tools/gen_index.py` desde las ramas "
        "reales del remoto. No la edites a mano: modifica `tools/systems.json` y "
        "vuelve a ejecutar el generador (la fecha de cada corrida queda en "
        "`logs/gen_index.log`)."
    )
    lines.append("")

    # --- Tabla de sistemas ---
    lines.append("### Sistemas (`local/*`)")
    lines.append("")
    lines.append("| Rama | Sistema | Origen local | SHA |")
    lines.append("|------|---------|--------------|-----|")
    if buckets["systems"]:
        for name, sha in buckets["systems"]:
            info = metadata.get(name, {})
            sistema = info.get("sistema", "_(pendiente: anade a tools/systems.json)_")
            origen = info.get("origen", "—")
            lines.append(f"| `{name}` | {sistema} | `{origen}` | `{sha}` |")
    else:
        lines.append("| _(ninguna)_ | | | |")
    lines.append("")

    # --- Ramas de revision / efimeras ---
    lines.append("### Ramas de revision / efimeras (`review/*`, `wip/*`)")
    lines.append("")
    if buckets["review"]:
        for name, sha in buckets["review"]:
            lines.append(f"- `{name}` (`{sha}`) — temporal; no es un sistema publicado.")
    else:
        lines.append("- _(ninguna)_")
    lines.append("")

    # --- Comandos de clonado ---
    lines.append("### Uso rapido")
    lines.append("")
    lines.append("```bash")
    if buckets["systems"]:
        for name, _ in buckets["systems"]:
            suffix = name.split("/", 1)[1]
            lines.append(
                f"git clone -b {name} {remote_url} Local-{suffix}"
            )
    else:
        lines.append("# (sin ramas local/* todavia)")
    lines.append("```")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Sustitucion en README
# ---------------------------------------------------------------------------
def replace_between_markers(readme_text: str, block: str) -> str:
    """Reemplaza el contenido entre BEGIN/END markers. Los marcadores deben existir."""
    start = readme_text.find(BEGIN_MARKER)
    end = readme_text.find(END_MARKER)
    if start == -1 or end == -1:
        raise ValueError(
            f"No se encontraron los marcadores {BEGIN_MARKER} / {END_MARKER} "
            "en el README. Anadelos donde deba ir la tabla auto-generada."
        )
    if end < start:
        raise ValueError("El marcador END aparece antes que el BEGIN en el README.")

    before = readme_text[: start + len(BEGIN_MARKER)]
    after = readme_text[end:]
    return f"{before}\n\n{block}\n\n{after}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Regenera el indice de sistemas del README.")
    p.add_argument("--remote", default="origin", help="Remoto git a consultar (def: origin).")
    p.add_argument("--readme", type=Path, default=DEFAULT_README, help="Ruta del README.")
    p.add_argument("--metadata", type=Path, default=DEFAULT_METADATA, help="Ruta de systems.json.")
    p.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help="Directorio de logs.")
    p.add_argument(
        "--check",
        action="store_true",
        help="No escribe: sale con codigo 1 si el README esta desfasado.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = setup_logging(args.log_dir)
    LOG.info("=== gen_index arranque (check=%s) ===", args.check)
    LOG.debug("Log en: %s", log_file)

    try:
        remote_url = subprocess.run(
            ["git", "config", "--get", f"remote.{args.remote}.url"],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() or f"<{args.remote}>"
    except subprocess.CalledProcessError:
        remote_url = f"<{args.remote}>"
    LOG.info("Remoto %s -> %s", args.remote, remote_url)

    try:
        branches = list_remote_branches(args.remote)
    except Exception:
        LOG.exception("No se pudieron listar las ramas remotas.")
        return 2

    buckets = classify(branches)
    metadata = load_metadata(args.metadata)

    # Avisa de sistemas sin metadatos (para no dejar descripciones pendientes).
    for name, _ in buckets["systems"]:
        if name not in metadata:
            LOG.warning("Sistema sin descripcion en systems.json: %s", name)

    block = render_block(buckets, metadata, remote_url)

    if not args.readme.exists():
        LOG.error("No existe el README: %s", args.readme)
        return 2

    current = args.readme.read_text(encoding="utf-8")
    try:
        updated = replace_between_markers(current, block)
    except ValueError as exc:
        LOG.error("%s", exc)
        return 2

    if updated == current:
        LOG.info("README ya esta al dia. Sin cambios.")
        LOG.info("=== gen_index fin (ok) ===")
        return 0

    if args.check:
        LOG.error("README DESFASADO. Ejecuta 'python3 tools/gen_index.py' para regenerar.")
        LOG.info("=== gen_index fin (desfasado) ===")
        return 1

    args.readme.write_text(updated, encoding="utf-8")
    LOG.info("README actualizado: %s", args.readme)
    LOG.info("=== gen_index fin (escrito) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
