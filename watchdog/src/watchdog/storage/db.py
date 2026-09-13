"""SQLite: incidentes, memoria de IOCs (aprendizaje real, no magico) y
serie historica de metricas para entrenar el detector de anomalias."""
import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    scan_mode TEXT NOT NULL,
    finding_type TEXT NOT NULL,      -- process|file|network|cert|other
    target TEXT NOT NULL,            -- path, ip, pid+cmdline, etc.
    sha256 TEXT,
    vt_positives INTEGER,
    vt_total INTEGER,
    otx_hit INTEGER,
    ip_rep_score INTEGER,
    action TEXT NOT NULL,            -- alert_only|quarantine|auto_delete
    forensics_path TEXT,
    llm_triage TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ioc_memory (
    ioc TEXT PRIMARY KEY,            -- sha256 o ip
    ioc_type TEXT NOT NULL,          -- hash|ip
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 1,
    last_verdict TEXT,
    intel_json TEXT
);

CREATE TABLE IF NOT EXISTS metrics_history (
    ts TEXT PRIMARY KEY,
    num_processes INTEGER,
    num_listening_ports INTEGER,
    num_connections INTEGER,
    num_unique_parents INTEGER,
    cpu_percent REAL,
    mem_percent REAL,
    num_unpackaged_exec_paths INTEGER
);

CREATE TABLE IF NOT EXISTS net_snapshot (
    key TEXT PRIMARY KEY,   -- "ports" o "hosts"
    payload_json TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cert_baseline (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS persistence_baseline (
    key TEXT PRIMARY KEY,   -- "sshkey:...", "sudoers:...", "crontab:user", "selfcode:..."
    sha256 TEXT NOT NULL,
    ts TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextlib.contextmanager
def connect(cfg):
    db_path = Path(cfg.get("paths", "db_path"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_incident(
    conn, *, scan_mode, finding_type, target, action,
    sha256=None, vt_positives=None, vt_total=None,
    otx_hit=None, ip_rep_score=None, forensics_path=None,
    llm_triage=None, notes=None,
) -> int:
    cur = conn.execute(
        """INSERT INTO incidents
           (ts, scan_mode, finding_type, target, sha256, vt_positives,
            vt_total, otx_hit, ip_rep_score, action, forensics_path,
            llm_triage, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now(), scan_mode, finding_type, target, sha256, vt_positives,
         vt_total, int(bool(otx_hit)) if otx_hit is not None else None,
         ip_rep_score, action, forensics_path, llm_triage, notes),
    )
    return cur.lastrowid


def remember_ioc(conn, ioc: str, ioc_type: str, verdict: str, intel: dict):
    now = _now()
    row = conn.execute("SELECT hit_count FROM ioc_memory WHERE ioc=?", (ioc,)).fetchone()
    if row:
        conn.execute(
            """UPDATE ioc_memory SET last_seen=?, hit_count=hit_count+1,
               last_verdict=?, intel_json=? WHERE ioc=?""",
            (now, verdict, json.dumps(intel), ioc),
        )
    else:
        conn.execute(
            """INSERT INTO ioc_memory
               (ioc, ioc_type, first_seen, last_seen, hit_count, last_verdict, intel_json)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (ioc, ioc_type, now, now, verdict, json.dumps(intel)),
        )


def recall_ioc(conn, ioc: str):
    row = conn.execute(
        "SELECT ioc_type, first_seen, last_seen, hit_count, last_verdict, intel_json "
        "FROM ioc_memory WHERE ioc=?", (ioc,)
    ).fetchone()
    if not row:
        return None
    keys = ["ioc_type", "first_seen", "last_seen", "hit_count", "last_verdict", "intel_json"]
    d = dict(zip(keys, row))
    d["intel_json"] = json.loads(d["intel_json"]) if d["intel_json"] else {}
    return d


def append_metrics(conn, metrics: dict):
    conn.execute(
        """INSERT OR REPLACE INTO metrics_history
           (ts, num_processes, num_listening_ports, num_connections,
            num_unique_parents, cpu_percent, mem_percent, num_unpackaged_exec_paths)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (_now(), metrics.get("num_processes"), metrics.get("num_listening_ports"),
         metrics.get("num_connections"), metrics.get("num_unique_parents"),
         metrics.get("cpu_percent"), metrics.get("mem_percent"),
         metrics.get("num_unpackaged_exec_paths")),
    )


def load_metrics_history(conn):
    cur = conn.execute(
        "SELECT num_processes, num_listening_ports, num_connections, "
        "num_unique_parents, cpu_percent, mem_percent, num_unpackaged_exec_paths "
        "FROM metrics_history ORDER BY ts"
    )
    return cur.fetchall()


def get_net_snapshot(conn, key: str):
    row = conn.execute("SELECT payload_json FROM net_snapshot WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def set_net_snapshot(conn, key: str, payload):
    conn.execute(
        "INSERT OR REPLACE INTO net_snapshot (key, payload_json, ts) VALUES (?, ?, ?)",
        (key, json.dumps(payload), _now()),
    )


def get_cert_baseline(conn) -> dict:
    cur = conn.execute("SELECT path, sha256 FROM cert_baseline")
    return {path: sha for path, sha in cur.fetchall()}


def set_cert_baseline(conn, path: str, sha256: str):
    conn.execute(
        "INSERT OR REPLACE INTO cert_baseline (path, sha256, ts) VALUES (?, ?, ?)",
        (path, sha256, _now()),
    )


def delete_cert_baseline(conn, path: str):
    conn.execute("DELETE FROM cert_baseline WHERE path=?", (path,))


def get_persistence_baseline(conn) -> dict:
    cur = conn.execute("SELECT key, sha256 FROM persistence_baseline")
    return {key: sha for key, sha in cur.fetchall()}


def set_persistence_baseline(conn, key: str, sha256: str):
    conn.execute(
        "INSERT OR REPLACE INTO persistence_baseline (key, sha256, ts) VALUES (?, ?, ?)",
        (key, sha256, _now()),
    )


def delete_persistence_baseline(conn, key: str):
    conn.execute("DELETE FROM persistence_baseline WHERE key=?", (key,))
