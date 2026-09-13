#!/usr/bin/env python3
"""Punto de entrada del watchdog. Invocado por cron:
  */15 * * * *  python main.py --mode light
  0 * * * *     python main.py --mode heavy   (light + escaneos pesados +
                                                 auditoria de integridad al final)
"""
import argparse
import sys

import psutil

from . import config as cfgmod
from . import notify, util
from .anomaly import detector
from .intel import alienvault_otx, ip_reputation, virustotal
from .response import policy, quarantine
from .scanners import host_scan, integrity_scan, network_scan, os_scan, persistence_scan
from .storage import db
from .llm import triage as llm_triage


def enrich_hash(cfg, sha256: str) -> dict:
    keys = cfg.api_keys
    timeout = cfg.get("intel", "request_timeout_seconds", default=15)

    vt = None
    if cfg.get("intel", "vt_enabled", default=True):
        vt = virustotal.lookup_hash(keys["virustotal"], sha256, timeout)

    otx = None
    if cfg.get("intel", "otx_enabled", default=True):
        otx = alienvault_otx.lookup_hash(keys["otx"], sha256, timeout)

    return {"vt": vt, "otx": otx}


def enrich_ip(cfg, ip: str) -> dict:
    keys = cfg.api_keys
    timeout = cfg.get("intel", "request_timeout_seconds", default=15)

    otx = None
    if cfg.get("intel", "otx_enabled", default=True):
        otx = alienvault_otx.lookup_ip(keys["otx"], ip, timeout)

    ip_rep = None
    if cfg.get("intel", "ip_rep_enabled", default=True):
        ip_rep = ip_reputation.check_ip(keys["abuseipdb"], ip, timeout)

    return {"otx": otx, "ip_rep": ip_rep}


def handle_process_finding(cfg, conn, logger, scan_mode: str, finding: dict):
    proc = finding.get("proc")
    if proc is None or not proc.is_running():
        return
    exe = None
    try:
        exe = proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    pipeline = host_scan.process_pipeline(proc)
    forensics_path = host_scan.save_forensics(cfg, finding["target"], pipeline)
    logger.info(f"[main] forense guardado: {forensics_path}")

    sha256 = util.sha256_file(exe) if exe else None
    intel = enrich_hash(cfg, sha256) if sha256 else {"vt": None, "otx": None}

    action = policy.decide(cfg, intel)
    quarantine_path = None
    if exe:
        quarantine_path, sha256_confirmed = quarantine.quarantine_file(cfg, logger, exe)
        sha256 = sha256 or sha256_confirmed
    quarantine.kill_process(logger, proc.pid)

    if action == policy.AUTO_DELETE and quarantine_path:
        quarantine.permanently_delete(logger, quarantine_path)

    note = None
    if cfg.get("llm", "enabled", default=False):
        note = llm_triage.triage(cfg, finding, intel, action)

    db.record_incident(
        conn, scan_mode=scan_mode, finding_type="process", target=finding["target"],
        action=action, sha256=sha256,
        vt_positives=(intel.get("vt") or {}).get("positives"),
        vt_total=(intel.get("vt") or {}).get("total"),
        otx_hit=(intel.get("otx") or {}).get("hit"),
        forensics_path=forensics_path, llm_triage=note, notes=finding["detail"],
    )
    if sha256:
        db.remember_ioc(conn, sha256, "hash", action, intel)

    notify.telegram_notify(
        cfg, f"[watchdog] {finding['detail']}\ntarget={finding['target']}\naccion={action}"
    )


def handle_network_finding(cfg, conn, logger, scan_mode: str, finding: dict):
    target = finding["target"]
    ip = target.split(":")[0].strip("[]") if ":" in target and not target.count(":") > 1 else target
    intel = enrich_ip(cfg, ip)

    note = None
    if cfg.get("llm", "enabled", default=False):
        note = llm_triage.triage(cfg, finding, intel, policy.ALERT_ONLY)

    db.record_incident(
        conn, scan_mode=scan_mode, finding_type="network", target=target,
        action=policy.ALERT_ONLY,
        otx_hit=(intel.get("otx") or {}).get("hit"),
        ip_rep_score=(intel.get("ip_rep") or {}).get("abuse_score"),
        llm_triage=note, notes=finding["detail"],
    )
    db.remember_ioc(conn, ip, "ip", policy.ALERT_ONLY, intel)
    notify.telegram_notify(cfg, f"[watchdog] red: {finding['detail']} ({target})")


def handle_generic_finding(conn, scan_mode: str, finding: dict):
    """Hallazgos de os_scan (rkhunter/chkrootkit/clamscan) y de cert_audit:
    siempre alert_only, nunca accion automatica (ver README: borrar un
    certificado de confianza solo puede hacerlo un humano)."""
    db.record_incident(
        conn, scan_mode=scan_mode, finding_type=finding["type"], target=finding["target"],
        action=policy.ALERT_ONLY, notes=finding["detail"],
    )


def run_light(cfg, conn, logger):
    findings = []
    findings += network_scan.quick(conn, logger)
    host_findings, metrics = host_scan.quick(cfg, logger)
    findings += host_findings
    db.append_metrics(conn, metrics)

    model = detector.load_model(cfg.get("paths", "model_path"))
    if model is not None:
        s = detector.score(model, metrics)
        if s is not None and s < 0:
            logger.warning(f"[anomaly] score fuera de baseline: {s:.4f} metrics={metrics}")
            db.record_incident(
                conn, scan_mode="light", finding_type="anomaly", target="system_metrics",
                action=policy.ALERT_ONLY, notes=f"isolation_forest_score={s:.4f}",
            )
    else:
        logger.info("[anomaly] sin modelo entrenado todavia (correr scripts/train_baseline.py)")

    for f in findings:
        if f["type"] == "process":
            handle_process_finding(cfg, conn, logger, "light", f)
        elif f["type"] == "network":
            handle_network_finding(cfg, conn, logger, "light", f)
    return findings


def run_heavy(cfg, conn, logger):
    findings = run_light(cfg, conn, logger)

    findings_deep = network_scan.deep(conn, cfg, logger)
    for f in findings_deep:
        handle_network_finding(cfg, conn, logger, "heavy", f)

    exclude = cfg.get("exclude_paths", default=[])
    clamscan_targets = cfg.get("clamscan_targets", default=["/home"])

    for w in os_scan.run_rkhunter(logger):
        f = {"type": "rkhunter", "target": w[:200], "detail": w}
        handle_generic_finding(conn, "heavy", f)
    for w in os_scan.run_chkrootkit(logger, exclude):
        f = {"type": "chkrootkit", "target": w[:200], "detail": w}
        handle_generic_finding(conn, "heavy", f)
    clam_timeout = cfg.get("clamscan_timeout_seconds", default=1200)
    for w in os_scan.run_clamscan(logger, clamscan_targets, timeout=clam_timeout):
        f = {"type": "clamscan", "target": w[:200], "detail": w}
        handle_generic_finding(conn, "heavy", f)

    logger.info("[main] auditoria de integridad final: procesos, certificados, persistencia")
    for f in integrity_scan.process_path_audit(cfg, logger):
        handle_generic_finding(conn, "heavy", f)
    for f in integrity_scan.cert_audit(conn, logger):
        handle_generic_finding(conn, "heavy", f)
    for f in persistence_scan.run(conn, logger):
        handle_generic_finding(conn, "heavy", f)

    return findings + findings_deep



def _acquire_run_lock_or_exit():
    """Non-blocking flock to skip overlapping light/heavy runs."""
    import fcntl
    import logging
    import os
    import sys
    from pathlib import Path
    log = logging.getLogger("watchdog")
    lock_path = Path("/watchdog/data/watchdog.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.warning("another watchdog run holds %s; skipping overlap", lock_path)
        sys.exit(0)
    # keep fh alive for process lifetime
    _acquire_run_lock_or_exit._fh = fh  # type: ignore[attr-defined]


def main():

    _acquire_run_lock_or_exit()
    parser = argparse.ArgumentParser(description="SNT Watchdog - Kali security monitor")
    parser.add_argument("--mode", choices=["light", "heavy"], required=True)
    args = parser.parse_args()

    cfg = cfgmod.load_config()
    cfgmod.ensure_dirs(cfg)
    logger = notify.get_logger(cfg)

    logger.info(f"===== watchdog run mode={args.mode} =====")
    with db.connect(cfg) as conn:
        try:
            if args.mode == "light":
                run_light(cfg, conn, logger)
            else:
                run_heavy(cfg, conn, logger)
        except Exception:
            logger.exception("[main] fallo no controlado durante el escaneo")
            sys.exit(1)
    logger.info(f"===== watchdog run mode={args.mode} completado =====")


if __name__ == "__main__":
    main()
