#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificador del indice de sistemas locales (repo Inzainos/Local).

El README es un documento curado a mano (tablas de sistemas, snapshots, deuda
conocida). Este script NO lo reescribe: verifica que no se desfase respecto a
las ramas reales del remoto. Falla si aparece o desaparece una rama de sistema
(`local/*`) sin que el README lo refleje.

Clasificacion de ramas:
  - local/*            -> rama de sistema (debe estar documentada en el README)
  - review/* , wip/*   -> rama de revision / efimera (no se exige documentar)
  - main, claude/*     -> infraestructura (se ignora)

Uso:
  python3 tools/gen_index.py            # verifica; sale 1 si hay deriva
  python3 tools/gen_index.py --check    # identico (alias explicito para CI)
  python3 tools/gen_index.py --remote origin --readme README.md

Todos los logs quedan en logs/gen_index.log y en consola.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

# --- Rutas por defecto (relativas a la raiz del repo) -----------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_README = REPO_ROOT / "README.md"
DEFAULT_LOG_DIR = REPO_ROOT / "logs"

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
def list_remote_branches(remote: str) -> list[str]:
    """Devuelve la lista de ramas del remoto (nombres), ordenada.

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

    branches: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        _sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/heads/"):
            continue
        branches.append(ref[len("refs/heads/") :])

    branches.sort()
    LOG.info("Ramas remotas encontradas: %d", len(branches))
    for name in branches:
        LOG.debug("  %s", name)
    return branches


# ---------------------------------------------------------------------------
# Clasificacion
# ---------------------------------------------------------------------------
def system_branches(branches: list[str]) -> list[str]:
    """Filtra las ramas de sistema (local/*), avisando de las no clasificadas."""
    systems: list[str] = []
    for name in branches:
        if name in INFRA_EXACT or name.startswith(INFRA_PREFIXES):
            continue
        if name.startswith(SYSTEM_PREFIX):
            systems.append(name)
        elif name.startswith(REVIEW_PREFIXES):
            LOG.info("Rama de revision/efimera (no se exige documentar): %s", name)
        else:
            LOG.warning("Rama sin clasificar (ignorada): %s", name)
    LOG.info("Ramas de sistema (local/*): %d", len(systems))
    return systems


# ---------------------------------------------------------------------------
# Lectura del README
# ---------------------------------------------------------------------------
def documented_systems(readme_text: str) -> set[str]:
    """Extrae los nombres de rama local/* mencionados en el README."""
    found = set(re.findall(r"local/[A-Za-z0-9._\-]+", readme_text))
    LOG.info("Ramas local/* mencionadas en el README: %d", len(found))
    return found


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Verifica que el README documente las ramas de sistema reales."
    )
    p.add_argument("--remote", default="origin", help="Remoto git a consultar (def: origin).")
    p.add_argument("--readme", type=Path, default=DEFAULT_README, help="Ruta del README.")
    p.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help="Directorio de logs.")
    p.add_argument(
        "--check",
        action="store_true",
        help="Alias explicito para CI (el script ya sale 1 ante deriva).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = setup_logging(args.log_dir)
    LOG.info("=== gen_index (verificacion) arranque ===")
    LOG.debug("Log en: %s", log_file)

    if not args.readme.exists():
        LOG.error("No existe el README: %s", args.readme)
        return 2

    try:
        branches = list_remote_branches(args.remote)
    except Exception:
        LOG.exception("No se pudieron listar las ramas remotas.")
        return 2

    expected = set(system_branches(branches))
    documented = documented_systems(args.readme.read_text(encoding="utf-8"))

    missing = sorted(expected - documented)   # en el remoto, sin documentar
    orphan = sorted(documented - expected)     # documentadas, ya no en el remoto

    for name in missing:
        LOG.error("Rama de sistema SIN documentar en el README: %s", name)
    for name in orphan:
        LOG.error("Rama documentada que YA NO existe en el remoto: %s", name)

    if missing or orphan:
        LOG.error(
            "README DESFASADO: %d sin documentar, %d obsoletas. "
            "Actualiza el README para reflejar las ramas reales.",
            len(missing),
            len(orphan),
        )
        LOG.info("=== gen_index fin (desfasado) ===")
        return 1

    LOG.info("README al dia: las %d ramas de sistema estan documentadas.", len(expected))
    LOG.info("=== gen_index fin (ok) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
