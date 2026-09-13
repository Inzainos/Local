#!/usr/bin/env python3
"""
Sentinel Omega — Reboot
Gracefully shuts down the running orchestrator and relaunches it.

Usage:
    python sentinel_omega/reboot.py
    python sentinel_omega/reboot.py --dashboard     # Relaunch with dashboard
    python sentinel_omega/reboot.py --dry-run       # Relaunch without Telegram
    python sentinel_omega/reboot.py --force          # SIGKILL on stuck process
"""

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PIDFILE = Path(__file__).parent / "data" / "sentinel_omega.pid"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [REBOOT] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _read_pid() -> int:
    if not PIDFILE.exists():
        return 0
    try:
        return int(PIDFILE.read_text().strip())
    except (ValueError, OSError):
        return 0


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _stop_current(force: bool = False) -> bool:
    pid = _read_pid()

    if pid == 0 or not _process_alive(pid):
        if PIDFILE.exists():
            PIDFILE.unlink(missing_ok=True)
        logger.info("No running instance found.")
        return True

    logger.info(f"Stopping Sentinel Omega (PID {pid})...")
    os.kill(pid, signal.SIGTERM)

    for i in range(20):
        time.sleep(1)
        if not _process_alive(pid):
            logger.info(f"PID {pid} stopped.")
            PIDFILE.unlink(missing_ok=True)
            return True
        if i % 5 == 4:
            logger.info(f"Waiting... ({i + 1}s)")

    if force:
        logger.warning(f"SIGTERM timeout — sending SIGKILL to PID {pid}...")
        os.kill(pid, signal.SIGKILL)
        time.sleep(2)
        PIDFILE.unlink(missing_ok=True)
        return not _process_alive(pid)

    logger.error(f"Could not stop PID {pid}. Use --force.")
    return False


def _relaunch(args):
    launcher = Path(__file__).parent / "launcher.py"
    cmd = [sys.executable, str(launcher)]

    if args.dashboard:
        cmd.append("--dashboard")
    if args.dry_run:
        cmd.append("--dry-run")

    logger.info(f"Relaunching: {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        start_new_session=True,
        stdout=open(Path(__file__).parent / "data" / "sentinel_omega.log", "a"),
        stderr=subprocess.STDOUT,
    )

    time.sleep(2)

    if proc.poll() is None:
        logger.info(f"Sentinel Omega relaunched (PID {proc.pid}).")
    else:
        logger.error(f"Relaunch failed with exit code {proc.returncode}.")
        sys.exit(1)


def reboot(args):
    logger.info("=" * 50)
    logger.info("  SENTINEL OMEGA — REBOOT")
    logger.info("=" * 50)

    if not _stop_current(force=args.force):
        logger.error("Reboot aborted — could not stop current instance.")
        sys.exit(1)

    time.sleep(2)

    _relaunch(args)

    logger.info("Reboot complete.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sentinel Omega — Reboot (stop + relaunch)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="SIGKILL if graceful stop times out",
    )
    parser.add_argument(
        "--dashboard", action="store_true",
        help="Relaunch with the Streamlit dashboard",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Relaunch without Telegram alerts",
    )
    return parser.parse_args()


if __name__ == "__main__":
    reboot(parse_args())
