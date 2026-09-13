#!/usr/bin/env python3
"""Incremental USGS refetch for tbl_eventos_sismicos_fuente (safe, no wipe)."""
from __future__ import annotations
import argparse, logging, sqlite3
from datetime import datetime, timedelta, timezone
from io import StringIO
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sismos_refetch")
MIN_MAG = 2.5

def fetch_recent(days: int) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "csv",
        "starttime": start.strftime("%Y-%m-%d"),
        "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "minmagnitude": str(MIN_MAG),
    }
    r = requests.get(url, params=params, timeout=90)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
    return df[["id", "time", "mag", "latitude", "longitude"]].copy()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    df = fetch_recent(args.days)
    logger.info("USGS rows=%s", len(df))
    if df.empty:
        return
    try:
        from sentinel_omega.core.shared.geometria_uvg import nodo_mas_cercano
    except Exception:
        from core.shared.geometria_uvg import nodo_mas_cercano
    con = sqlite3.connect(args.db)
    n = 0
    for _, row in df.iterrows():
        nodo = nodo_mas_cercano(float(row["latitude"]), float(row["longitude"]))
        if not args.dry_run:
            con.execute(
                """INSERT INTO tbl_eventos_sismicos_fuente
                   (usgs_id, time_utc, lat, lon, mag, id_nodo, topologia_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(usgs_id) DO UPDATE SET
                       lat=excluded.lat, lon=excluded.lon, mag=excluded.mag,
                       id_nodo=excluded.id_nodo,
                       topologia_version=excluded.topologia_version,
                       updated_at=datetime('now')""",
                (str(row["id"]), str(row["time"]), float(row["latitude"]),
                 float(row["longitude"]), float(row["mag"]), nodo["id"], "incremental"),
            )
        n += 1
    if not args.dry_run:
        con.commit()
    mx = con.execute("SELECT MAX(time_utc), COUNT(*) FROM tbl_eventos_sismicos_fuente").fetchone()
    con.close()
    logger.info("upserted=%s max_time=%s total=%s", n, mx[0], mx[1])

if __name__ == "__main__":
    main()
