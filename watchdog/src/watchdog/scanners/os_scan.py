"""Wrappers de las herramientas de Kali ya validadas manualmente en la
auditoria: rkhunter, chkrootkit, clamscan. Corren SOLO en el ciclo pesado
(cada hora) porque son lentas. Requieren sudo -n (ver README: hay que dar
permiso NOPASSWD acotado a estos 3 binarios para que el cron no se cuelgue
pidiendo contrasena)."""
import re
import subprocess

WARNING_RE = re.compile(r"\[\s*Warning\s*\]", re.IGNORECASE)


def run_rkhunter(logger, timeout: int = 180) -> list[str]:
    try:
        out = subprocess.run(
            ["sudo", "-n", "rkhunter", "--check", "--sk", "--nocolors"],
            capture_output=True, text=True, timeout=timeout,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"[os_scan] rkhunter no se pudo correr (sudo NOPASSWD configurado?): {e}")
        return []
    warnings = [line.strip() for line in out.splitlines() if WARNING_RE.search(line)]
    return warnings


def run_chkrootkit(logger, exclude_dirs: list[str], timeout: int = 300) -> list[str]:
    try:
        out = subprocess.run(
            ["sudo", "-n", "chkrootkit"],
            capture_output=True, text=True, timeout=timeout,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"[os_scan] chkrootkit no se pudo correr: {e}")
        return []

    findings = []
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if "WARNING" not in line:
            continue
        # Filtra el ruido conocido: paquetes Debian legitimos y binarios de
        # entornos virtuales de Python (ver hallazgos de la auditoria manual).
        block = "\n".join(lines[i:i + 3])
        if "From Debian package" in block:
            continue
        if any(fnmatch_dir in block for fnmatch_dir in exclude_dirs):
            continue
        findings.append(line.strip())
    return findings


def run_clamscan(logger, targets: list[str], timeout: int = 1200) -> list[str]:
    try:
        out = subprocess.run(
            ["clamscan", '--exclude-dir=node_modules', '--exclude-dir=.venv', '--exclude-dir=venv', '--exclude-dir=.git', '--exclude-dir=.cache', '--exclude-dir=.npm', '--exclude-dir=site-packages', '--exclude-dir=dist-packages', "-r", "--infected", "--no-summary"] + targets,
            capture_output=True, text=True, timeout=timeout,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"[os_scan] clamscan no se pudo correr: {e}")
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]
