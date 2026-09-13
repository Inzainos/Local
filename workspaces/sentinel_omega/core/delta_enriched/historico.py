"""
Delta historical backfill — honest public series only.

Fills:
  - tbl_psique_financiera extra columns (vix, fear_greed, yield_spread, btc_dominance)
    joining onto existing daily BTC rows (2014-09-17 .. 2026-01-01)
  - tbl_delta_cross_historico from those joined series + measured composites
  - tbl_delta_fetch_log for every source attempt (ok/fail, n_rows, error)

Never invents numbers. A failed source is logged and that column stays NULL.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DDL_FETCH_LOG = """
CREATE TABLE IF NOT EXISTS tbl_delta_fetch_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 0,
    n_rows INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""

PSIQUE_EXTRA_COLS = [
    ("vix", "REAL"),
    ("fear_greed", "REAL"),
    ("yield_spread", "REAL"),
    ("btc_dominance", "REAL"),
    ("fetch_flags", "TEXT"),
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL_FETCH_LOG)
    existing = {r[1] for r in conn.execute("PRAGMA table_info(tbl_psique_financiera)")}
    for col, typ in PSIQUE_EXTRA_COLS:
        if col not in existing:
            conn.execute(f"ALTER TABLE tbl_psique_financiera ADD COLUMN {col} {typ}")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_delta_cross_historico (
            timestamp_blk            TEXT PRIMARY KEY,
            cross_coupling           REAL,
            geomagnetic_coupling     REAL,
            schumann_coupling        REAL,
            sentiment_coupling       REAL,
            composite_score          REAL,
            regime_label             TEXT,
            confidence               REAL,
            data_completeness        REAL,
            geo_kp_max_3d            REAL,
            geo_storm_active         INTEGER,
            geo_schumann_deviation   REAL,
            archivada_at             TEXT DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()


def log_fetch(conn: sqlite3.Connection, source: str, ok: bool, n_rows: int = 0, error: str = "") -> None:
    conn.execute(
        "INSERT INTO tbl_delta_fetch_log (source, ok, n_rows, error) VALUES (?,?,?,?)",
        (source, 1 if ok else 0, int(n_rows), error or None),
    )
    conn.commit()
    if ok:
        logger.info("Delta fetch %s: ok n=%s", source, n_rows)
    else:
        logger.warning("Delta fetch %s FAILED: %s", source, error)


def _http_json(url: str, timeout: int = 30) -> Any:
    from sentinel_omega.infrastructure.api._http import get_session
    resp = get_session().get(url, timeout=timeout, headers={"User-Agent": "SentinelOmega/2.6"})
    resp.raise_for_status()
    return resp.json()


def _http_text(url: str, timeout: int = 30) -> str:
    from sentinel_omega.infrastructure.api._http import get_session
    resp = get_session().get(url, timeout=timeout, headers={"User-Agent": "SentinelOmega/2.6"})
    resp.raise_for_status()
    return resp.text


def fetch_fgi_history() -> Tuple[Dict[str, float], Optional[str]]:
    """alternative.me Fear & Greed full history. day -> value 0..100."""
    url = "https://api.alternative.me/fng/?limit=0&format=json"
    try:
        payload = _http_json(url, timeout=45)
        rows = payload.get("data") or []
        out: Dict[str, float] = {}
        for row in rows:
            try:
                ts = int(row["timestamp"])
                day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                out[day] = float(row["value"])
            except (KeyError, TypeError, ValueError):
                continue
        return out, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def fetch_yahoo_history(symbol: str, day_from: str = "2014-01-01") -> Tuple[Dict[str, float], Optional[str]]:
    """Daily close via Yahoo chart API (no yfinance)."""
    try:
        t0 = int(datetime.strptime(day_from, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
        t1 = int(time.time())
        from sentinel_omega.infrastructure.api.crypto import fetch_yahoo_chart
        df = fetch_yahoo_chart(symbol, t0, t1, interval="1d")
        if df is None or df.empty:
            return {}, "empty yahoo frame"
        out: Dict[str, float] = {}
        for _, row in df.iterrows():
            ts = row.get("timestamp")
            close = row.get("close")
            if ts is None or close is None:
                continue
            try:
                day = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
                out[day] = float(close)
            except (TypeError, ValueError):
                continue
        return out, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def fetch_t10y2y_fred() -> Tuple[Dict[str, float], Optional[str]]:
    """10Y-2Y Treasury spread from FRED public CSV (no API key)."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y"
    try:
        text = _http_text(url, timeout=45)
        out: Dict[str, float] = {}
        for i, line in enumerate(text.splitlines()):
            if i == 0 or not line.strip():
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            day, val = parts[0].strip(), parts[1].strip()
            if val in (".", "", "NA"):
                continue
            try:
                out[day] = float(val)
            except ValueError:
                continue
        if not out:
            return {}, "empty FRED T10Y2Y"
        return out, None
    except Exception as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _day_of(ts_blk: str) -> str:
    return str(ts_blk)[:10]


def _composite_from_row(vix, fgi, spread, btc_vol) -> Tuple[float, str, float, float]:
    """Honest composite from whatever columns are present. completeness = fraction measured."""
    parts = []
    if fgi is not None:
        if fgi < 20:
            parts.append(0.4)
        elif fgi > 80:
            parts.append(0.3)
        else:
            parts.append(0.05)
    if vix is not None:
        if vix > 35:
            parts.append(0.4)
        elif vix < 12:
            parts.append(0.15)
        else:
            parts.append(min(0.25, max(0.0, (vix - 15.0) / 80.0)))
    if spread is not None and spread < 0:
        parts.append(0.2)
    if btc_vol is not None and btc_vol >= 5:
        parts.append(min(0.2, btc_vol / 50.0))
    n_possible = 4
    n_have = sum(1 for x in (vix, fgi, spread, btc_vol) if x is not None)
    completeness = n_have / n_possible
    score = min(1.0, sum(parts)) if parts else 0.0
    if completeness <= 0.0:
        regime = "NO_DATA"
        conf = 0.0
    elif score >= 0.6:
        regime = "STRESS"
        conf = min(0.85, 0.2 + 0.2 * n_have + 0.4 * score)
    elif score >= 0.35:
        regime = "ELEVATED"
        conf = min(0.85, 0.2 + 0.2 * n_have + 0.4 * score)
    elif completeness < 0.5:
        regime = "INCOMPLETE"
        conf = min(0.2, 0.05 + 0.05 * n_have)
    else:
        regime = "EQUILIBRIUM"
        conf = min(0.85, 0.2 + 0.2 * n_have + 0.4 * score)
    return score, regime, conf, completeness


def backfill(db_path: str) -> Dict[str, Any]:
    """Join public series onto psique BTC days and write historico. DEV-safe."""
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)
    stats: Dict[str, Any] = {"psique_updated": 0, "historico_written": 0, "sources": {}}

    fgi, err = fetch_fgi_history()
    log_fetch(conn, "alternative.me/fng", bool(fgi) and err is None, len(fgi), err or "")
    stats["sources"]["fgi"] = {"n": len(fgi), "error": err}

    vix, err = fetch_yahoo_history("^VIX", "2014-01-01")
    log_fetch(conn, "yahoo/^VIX", bool(vix) and err is None, len(vix), err or "")
    stats["sources"]["vix"] = {"n": len(vix), "error": err}

    spread, err = fetch_t10y2y_fred()
    if err or not spread:
        tnx, e1 = fetch_yahoo_history("^TNX", "2014-01-01")
        irx, e2 = fetch_yahoo_history("^IRX", "2014-01-01")
        log_fetch(conn, "fred/T10Y2Y", False, 0, err or "empty")
        if tnx and irx:
            spread = {}
            for d, y10 in tnx.items():
                if d in irx:
                    spread[d] = y10 - irx[d]
            log_fetch(conn, "yahoo/^TNX-^IRX", True, len(spread), "")
            err = None
        else:
            log_fetch(conn, "yahoo/^TNX-^IRX", False, 0, f"{e1}|{e2}")
            err = err or e1 or e2
            spread = spread or {}
    else:
        log_fetch(conn, "fred/T10Y2Y", True, len(spread), "")
    stats["sources"]["yield_spread"] = {"n": len(spread), "error": err}

    rows = conn.execute(
        "SELECT timestamp_blk, btc_precio_usd, volatilidad_24h FROM tbl_psique_financiera"
    ).fetchall()

    hist_n = 0
    upd_n = 0
    for ts_blk, precio, vol in rows:
        day = _day_of(ts_blk)
        vix_v = vix.get(day)
        fgi_v = fgi.get(day)
        spr_v = spread.get(day)
        flags = {
            "vix": vix_v is not None,
            "fear_greed": fgi_v is not None,
            "yield_spread": spr_v is not None,
            "btc": precio is not None,
        }
        conn.execute(
            "UPDATE tbl_psique_financiera SET vix=?, fear_greed=?, yield_spread=?, fetch_flags=? "
            "WHERE timestamp_blk=?",
            (vix_v, fgi_v, spr_v, json.dumps(flags), ts_blk),
        )
        upd_n += 1
        score, regime, conf, complete = _composite_from_row(vix_v, fgi_v, spr_v, vol)
        # sentiment_coupling uses FGI when present; others stay NULL (no invention)
        sentiment = None
        if fgi_v is not None:
            sentiment = abs(fgi_v - 50.0) / 50.0
        conn.execute(
            "INSERT OR REPLACE INTO tbl_delta_cross_historico "
            "(timestamp_blk, cross_coupling, geomagnetic_coupling, schumann_coupling, "
            " sentiment_coupling, composite_score, regime_label, confidence, "
            " data_completeness, geo_kp_max_3d, geo_storm_active, geo_schumann_deviation) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ts_blk, None, None, None, sentiment, score, regime, conf, complete,
                None, 0, None,
            ),
        )
        hist_n += 1
        if upd_n % 500 == 0:
            conn.commit()

    conn.commit()
    stats["psique_updated"] = upd_n
    stats["historico_written"] = hist_n
    n_hist = conn.execute("SELECT COUNT(*) FROM tbl_delta_cross_historico").fetchone()[0]
    n_nonzero = conn.execute(
        "SELECT COUNT(*) FROM tbl_delta_cross_historico WHERE composite_score > 0"
    ).fetchone()[0]
    n_vix = conn.execute("SELECT COUNT(*) FROM tbl_psique_financiera WHERE vix IS NOT NULL").fetchone()[0]
    n_fgi = conn.execute("SELECT COUNT(*) FROM tbl_psique_financiera WHERE fear_greed IS NOT NULL").fetchone()[0]
    n_spr = conn.execute("SELECT COUNT(*) FROM tbl_psique_financiera WHERE yield_spread IS NOT NULL").fetchone()[0]
    stats["historico_total"] = n_hist
    stats["historico_nonzero_score"] = n_nonzero
    stats["psique_vix"] = n_vix
    stats["psique_fgi"] = n_fgi
    stats["psique_yield"] = n_spr
    conn.close()
    logger.info("Delta historico backfill: %s", stats)
    return stats


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [DELTA_HIST] %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", required=True)
    args = ap.parse_args()
    print(json.dumps(backfill(args.db_path), indent=2, default=str))
