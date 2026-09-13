"""Monitoreo de vectores de persistencia clasicos post-compromiso:
authorized_keys, sudoers.d, crontab del usuario, y el propio codigo de
watchdog (self-integrity). Corre en el ciclo pesado, siempre ALERT_ONLY -
nunca se revierte nada automaticamente aca, porque un falso positivo
"arreglando" sudoers o cron puede dejar el sistema roto o sin acceso.

Limitacion honesta: si un atacante ya tiene root, tambien puede alterar
watchdog.db (el baseline) y este chequeo deja de ser confiable. Es una
capa de deteccion temprana, no una garantia criptografica - para eso
haria falta firmar el baseline y guardarlo fuera de esta maquina (ver
scripts/offbox_backup.sh, que al menos deja una copia fuera del alcance
de un compromiso puramente en Linux)."""
import subprocess
from pathlib import Path

from ..storage import db
from ..util import sha256_file

SUDOERS_DIR = Path("/etc/sudoers.d")
SSH_KEY_FILES = [Path.home() / ".ssh" / "authorized_keys"]
WATCHDOG_SRC = Path(__file__).resolve().parents[2]  # src/watchdog/../.. -> src


def _hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def _current_crontab() -> str | None:
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    return out.stdout if out.returncode == 0 else ""


def _collect_current(logger) -> dict[str, str]:
    current = {}

    for key_file in SSH_KEY_FILES:
        if key_file.exists():
            sha = sha256_file(str(key_file))
            if sha:
                current[f"sshkey:{key_file}"] = sha

    if SUDOERS_DIR.exists():
        for f in SUDOERS_DIR.glob("*"):
            if f.is_file():
                sha = sha256_file(str(f))
                if sha:
                    current[f"sudoers:{f}"] = sha

    crontab_text = _current_crontab()
    if crontab_text is not None:
        current["crontab:user"] = _hash_text(crontab_text)

    for py_file in WATCHDOG_SRC.rglob("*.py"):
        sha = sha256_file(str(py_file))
        if sha:
            current[f"selfcode:{py_file}"] = sha

    return current


def run(conn, logger) -> list[dict]:
    baseline = db.get_persistence_baseline(conn)
    current = _collect_current(logger)

    findings = []
    if baseline:
        added = set(current) - set(baseline)
        removed = set(baseline) - set(current)
        changed = {k for k in (set(current) & set(baseline)) if current[k] != baseline[k]}

        for k in added:
            detail = "nuevo elemento de persistencia (no estaba en baseline)"
            findings.append({"type": "persistence", "target": k, "detail": detail})
            logger.warning(f"[persistence] nuevo: {k}")
        for k in changed:
            detail = "elemento de persistencia MODIFICADO"
            findings.append({"type": "persistence", "target": k, "detail": detail})
            logger.warning(f"[persistence] MODIFICADO: {k}")
        for k in removed:
            detail = "elemento de persistencia eliminado"
            findings.append({"type": "persistence", "target": k, "detail": detail})
            logger.info(f"[persistence] eliminado: {k}")
            db.delete_persistence_baseline(conn, k)

    for key, sha in current.items():
        db.set_persistence_baseline(conn, key, sha)

    return findings
