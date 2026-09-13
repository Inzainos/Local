"""Auditoria de integridad: paths de binarios en ejecucion vs lo que dpkg
dice que deberia haber instalado (paths originales vs instalados), y
certificados de confianza vs baseline guardado (detecta inyeccion de CA
para MITM). Corre al final del ciclo pesado, como pidio el usuario."""
import fnmatch
import subprocess
from pathlib import Path

import psutil

from ..storage import db
from ..util import sha256_file as _sha256_file

CERT_DIRS = ["/etc/ssl/certs", "/usr/local/share/ca-certificates"]


def _is_excluded(path: str, exclude_patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in exclude_patterns)


def _dpkg_owner(path: str) -> str | None:
    try:
        out = subprocess.run(
            ["dpkg", "-S", path], capture_output=True, text=True, timeout=10
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.split(":")[0].strip()


def process_path_audit(cfg, logger) -> list[dict]:
    """Procesos vivos cuyo binario NO pertenece a ningun paquete Debian y
    no esta en la lista de exclusion (venvs, node_modules, /watchdog, etc)."""
    exclude = cfg.get("exclude_paths", default=[])
    checked, findings = set(), []

    for proc in psutil.process_iter(["exe"]):
        try:
            exe = proc.info.get("exe") or ""
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not exe or exe in checked or _is_excluded(exe, exclude):
            continue
        checked.add(exe)

        owner = _dpkg_owner(exe)
        if owner is None:
            findings.append({
                "type": "process",
                "target": f"pid={proc.pid} exe={exe}",
                "detail": "binario no pertenece a ningun paquete dpkg conocido",
            })
            logger.info(f"[integrity] binario no empaquetado en ejecucion: {exe}")

    return findings


def cert_audit(conn, logger) -> list[dict]:
    """Compara hashes de los certificados de confianza contra el baseline
    guardado. Primera corrida solo establece el baseline."""
    baseline = db.get_cert_baseline(conn)
    current = {}

    for cert_dir in CERT_DIRS:
        p = Path(cert_dir)
        if not p.exists():
            continue
        for f in p.glob("*"):
            if f.is_file():
                sha = _sha256_file(str(f))
                if sha:
                    current[str(f)] = sha

    findings = []
    if baseline:
        added = set(current) - set(baseline)
        removed = set(baseline) - set(current)
        changed = {p for p in (set(current) & set(baseline)) if current[p] != baseline[p]}

        for p in added:
            detail = "certificado nuevo, no estaba en el baseline"
            findings.append({"type": "cert", "target": p, "detail": detail})
            logger.info(f"[integrity] certificado nuevo: {p}")
        for p in changed:
            findings.append({"type": "cert", "target": p, "detail": "certificado modificado"})
            logger.warning(f"[integrity] certificado MODIFICADO: {p}")
        for p in removed:
            detail = "certificado eliminado del store"
            findings.append({"type": "cert", "target": p, "detail": detail})
            logger.info(f"[integrity] certificado eliminado: {p}")
            db.delete_cert_baseline(conn, p)

    for path, sha in current.items():
        db.set_cert_baseline(conn, path, sha)

    return findings
