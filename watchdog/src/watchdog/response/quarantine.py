"""Ejecuta la cuarentena: mueve el archivo, lo deja illegible (chmod 000),
mata el proceso si sigue vivo, y deja registro para poder restaurar. El
borrado definitivo (auto_delete) SIEMPRE pasa primero por aca."""
import os
import shutil
import time
from pathlib import Path

import psutil

from ..util import sha256_file as _sha256_file


def quarantine_file(cfg, logger, path: str) -> tuple[str | None, str | None]:
    """Devuelve (ruta_en_cuarentena, sha256) o (None, None) si no se pudo."""
    src = Path(path)
    if not src.exists() or not src.is_file():
        return None, None

    sha256 = _sha256_file(str(src))
    q_dir = Path(cfg.get("paths", "quarantine_dir"))
    q_dir.mkdir(parents=True, exist_ok=True)
    dest = q_dir / f"{int(time.time())}_{sha256 or 'nohash'}_{src.name}"

    try:
        shutil.move(str(src), str(dest))
        os.chmod(dest, 0o000)
        logger.warning(f"[quarantine] {src} -> {dest} (chmod 000)")
        return str(dest), sha256
    except (OSError, PermissionError) as e:
        logger.error(f"[quarantine] no se pudo mover {src}: {e}")
        return None, sha256


def kill_process(logger, pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        p.kill()
        logger.warning(f"[quarantine] proceso pid={pid} ({p.name()}) terminado")
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.error(f"[quarantine] no se pudo matar pid={pid}: {e}")
        return False


def permanently_delete(logger, quarantine_path: str):
    """SOLO se llama despues de que el hallazgo ya paso por quarantine_file
    Y la politica decidio auto_delete con confianza muy alta. El registro
    completo (hash, intel, forense) ya quedo en incidents antes de esto."""
    try:
        os.chmod(quarantine_path, 0o600)
        os.remove(quarantine_path)
        logger.warning(f"[quarantine] borrado definitivo: {quarantine_path}")
    except (OSError, PermissionError) as e:
        logger.error(f"[quarantine] no se pudo borrar {quarantine_path}: {e}")


def restore(logger, quarantine_path: str, original_path: str) -> bool:
    """Restauracion manual (falso positivo). No se llama automaticamente."""
    try:
        os.chmod(quarantine_path, 0o644)
        shutil.move(quarantine_path, original_path)
        logger.info(f"[quarantine] restaurado: {quarantine_path} -> {original_path}")
        return True
    except (OSError, PermissionError) as e:
        logger.error(f"[quarantine] no se pudo restaurar: {e}")
        return False
