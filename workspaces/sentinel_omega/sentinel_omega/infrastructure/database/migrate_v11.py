"""Apply schema v11 deltas (locf, catalogo, lags). Call from init_database if version < 11."""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger(__name__)

V11_SQL = """
CREATE TABLE IF NOT EXISTS tbl_eventos_catalogo (
    event_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT    NOT NULL,
    event_class   TEXT    NOT NULL,
    id_nodo       INTEGER,
    lat           REAL,
    lon           REAL,
    intensidad    REAL    DEFAULT 0.0,
    fuente        TEXT    DEFAULT '',
    UNIQUE(timestamp_utc, event_class, id_nodo, fuente)
);
CREATE INDEX IF NOT EXISTS idx_eventos_cat_class ON tbl_eventos_catalogo(event_class);
CREATE INDEX IF NOT EXISTS idx_eventos_cat_ts ON tbl_eventos_catalogo(timestamp_utc);

CREATE TABLE IF NOT EXISTS tbl_lag_anticipacion (
    event_class     TEXT PRIMARY KEY,
    lag_promedio_h  REAL,
    lag_max_h       REAL,
    lag_min_h       REAL,
    lag_p95_h       REAL,
    n_eventos       INTEGER DEFAULT 0,
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tbl_locf_cache (
    source_key   TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_locf_updated ON tbl_locf_cache(updated_at);

CREATE TABLE IF NOT EXISTS tbl_volcado_vivo_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at TEXT DEFAULT (datetime('now')),
    stats_json TEXT,
    cascada_ok INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tbl_schumann_vivo (
    timestamp_blk TEXT PRIMARY KEY,
    amplitude REAL,
    frequency REAL,
    source TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_schumann_vivo_ts ON tbl_schumann_vivo(timestamp_blk);
"""


def apply_v11(conn: sqlite3.Connection) -> None:
    conn.executescript(V11_SQL)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tbl_lag_anticipacion)").fetchall()}
        if cols and "lag_p95_h" not in cols:
            conn.execute("ALTER TABLE tbl_lag_anticipacion ADD COLUMN lag_p95_h REAL")
    except sqlite3.Error:
        pass
    try:
        conn.execute("INSERT OR REPLACE INTO TBL_SCHEMA_VERSION(version) VALUES(11)")
    except sqlite3.Error:
        pass
    conn.commit()
    logger.info("schema v11 deltas applied")
