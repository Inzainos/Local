"""Escaneo de equipo: procesos sospechosos (rutas raras, binario borrado en
disco pero proceso vivo) + captura de 'pipeline' forense (cadena de padres,
archivos abiertos, conexiones) para cualquier proceso flaggeado, ANTES de
tocarlo. Tambien junta las metricas que alimentan el detector de anomalias."""
import fnmatch
import time
from pathlib import Path

import psutil

SUSPICIOUS_PATH_PREFIXES = ("/tmp", "/dev/shm", "/var/tmp")
KNOWN_SAFE_PREFIXES = ("/watchdog",)


def _is_excluded(path: str, exclude_patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in exclude_patterns)


def process_pipeline(proc: psutil.Process) -> dict:
    """Reconstruye la cadena de ejecucion de un proceso: de donde vino, que
    tiene abierto, con quien habla en red. Esto es lo que se guarda en
    forensics/ antes de poner cualquier cosa en cuarentena."""
    chain = []
    p = proc
    try:
        while p is not None:
            chain.append({
                "pid": p.pid,
                "name": p.name(),
                "cmdline": " ".join(p.cmdline()),
                "exe": _safe(p.exe),
                "username": _safe(p.username),
                "create_time": p.create_time(),
            })
            p = p.parent()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    try:
        open_files = [f.path for f in proc.open_files()]
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        open_files = []

    try:
        conns = [
            {"laddr": str(c.laddr), "raddr": str(c.raddr), "status": c.status}
            for c in proc.net_connections(kind="inet")
        ]
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        conns = []

    return {"parent_chain": chain, "open_files": open_files, "connections": conns}


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def quick(cfg, logger) -> tuple[list[dict], dict]:
    """Escaneo liviano de procesos + metricas para el baseline de anomalias."""
    exclude = cfg.get("exclude_paths", default=[])
    findings = []
    unique_parents = set()

    for proc in psutil.process_iter(["pid", "name", "exe", "ppid"]):
        try:
            exe = proc.info.get("exe") or ""
            unique_parents.add(proc.info.get("ppid"))

            if not exe:
                continue
            if _is_excluded(exe, exclude) or exe.startswith(KNOWN_SAFE_PREFIXES):
                continue

            deleted = "(deleted)" in exe
            suspicious_path = exe.startswith(SUSPICIOUS_PATH_PREFIXES)

            if deleted or suspicious_path:
                detail = ("binario borrado en disco" if deleted
                          else "ejecutandose desde ruta temporal")
                findings.append({
                    "type": "process",
                    "target": f"pid={proc.pid} exe={exe}",
                    "detail": detail,
                    "proc": proc,
                })
                logger.info(f"[host:quick] proceso sospechoso pid={proc.pid} exe={exe}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    try:
        listening = sum(1 for c in psutil.net_connections(kind="inet") if c.status == "LISTEN")
        total_conns = len(psutil.net_connections(kind="inet"))
    except (psutil.AccessDenied, Exception):
        listening, total_conns = 0, 0

    metrics = {
        "num_processes": len(psutil.pids()),
        "num_listening_ports": listening,
        "num_connections": total_conns,
        "num_unique_parents": len(unique_parents),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "mem_percent": psutil.virtual_memory().percent,
    }
    return findings, metrics


def save_forensics(cfg, target_label: str, pipeline: dict) -> str:
    forensics_dir = Path(cfg.get("paths", "forensics_dir"))
    forensics_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(c if c.isalnum() else "_" for c in target_label)[:80]
    out_path = forensics_dir / f"{int(time.time())}_{safe_label}.json"
    import json
    out_path.write_text(json.dumps(pipeline, indent=2, default=str))
    return str(out_path)
