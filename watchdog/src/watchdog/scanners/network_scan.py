"""Escaneo de red: liviano (puertos propios en escucha) y pesado (nmap sobre
la subred local). Compara contra el ultimo snapshot guardado en SQLite para
detectar SOLO lo nuevo (puerto que se abrio, host que aparecio)."""
import subprocess

from ..storage import db


def _listening_ports() -> set[str]:
    try:
        out = subprocess.run(["ss", "-tlnH"], capture_output=True, text=True, timeout=15).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return set()
    ports = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            ports.add(parts[3])  # local address:port
    return ports


def quick(conn, logger) -> list[dict]:
    """Cada 15 min: diff de puertos en escucha vs la corrida anterior."""
    current = _listening_ports()
    previous = db.get_net_snapshot(conn, "ports")
    db.set_net_snapshot(conn, "ports", sorted(current))

    findings = []
    if previous is not None:
        new_ports = current - set(previous)
        for p in new_ports:
            findings.append({"type": "network", "target": p, "detail": "nuevo puerto en escucha"})
            logger.info(f"[network:quick] nuevo puerto en escucha: {p}")
    return findings


def deep(conn, cfg, logger) -> list[dict]:
    """Cada hora: nmap sobre la subred local configurada. Requiere que nmap
    tenga cap_net_raw (default en Kali) para no necesitar sudo."""
    cidr = cfg.get("network", "local_cidr")
    timeout = cfg.get("network", "nmap_timeout_seconds", default=240)
    try:
        out = subprocess.run(
            ["nmap", "-sn", "-T4", cidr],
            capture_output=True, text=True, timeout=timeout,
        ).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"[network:deep] nmap fallo: {e}")
        return []

    hosts = []
    for line in out.splitlines():
        if line.startswith("Nmap scan report for"):
            hosts.append(line.replace("Nmap scan report for ", "").strip())

    previous = db.get_net_snapshot(conn, "hosts")
    db.set_net_snapshot(conn, "hosts", hosts)

    findings = []
    if previous is not None:
        new_hosts = set(hosts) - set(previous)
        for h in new_hosts:
            findings.append({"type": "network", "target": h, "detail": "nuevo host en la red"})
            logger.info(f"[network:deep] nuevo host detectado: {h}")
    return findings
