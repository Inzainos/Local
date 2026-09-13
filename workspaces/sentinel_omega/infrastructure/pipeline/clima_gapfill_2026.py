#!/usr/bin/env python3
"""One-shot fill tbl_clima_espacial_raw 2026 hours from NOAA feeds (fail-soft)."""
from __future__ import annotations
import argparse, json, logging, sqlite3, urllib.request
from collections import defaultdict
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("clima_gapfill")

KP_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
PLASMA_URLS = [
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_wind_1m.json",
    "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json",
]
MAG_URLS = [
    "https://services.swpc.noaa.gov/json/rtsw/rtsw_mag_1m.json",
    "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json",
]

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SentinelOmega/2.5"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def first_ok(urls):
    for u in urls:
        try:
            data = get_json(u)
            log.info("OK %s", u)
            return data, u
        except Exception as e:
            log.warning("FAIL %s: %s", u, e)
    return None, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    kp = get_json(KP_URL)
    plasma, _ = first_ok(PLASMA_URLS)
    mag, _ = first_ok(MAG_URLS)
    buckets = defaultdict(lambda: {"bz": [], "speed": [], "kp": []})

    for row in kp:
        ts = row.get("time_tag") or ""
        val = row.get("kp_index", row.get("kp"))
        if not ts.startswith("2026") or val is None:
            continue
        blk = ts[:13].replace("T", " ") + ":00"
        try:
            buckets[blk]["kp"].append(float(val))
        except Exception:
            pass

    # rtsw wind dict rows OR products array
    if isinstance(plasma, list) and plasma:
        if isinstance(plasma[0], dict):
            for row in plasma:
                ts = str(row.get("time_tag") or row.get("time") or "")
                if not ts.startswith("2026"):
                    continue
                blk = ts[:13].replace("T", " ") + ":00"
                speed = row.get("proton_speed", row.get("speed"))
                if speed is not None:
                    try:
                        buckets[blk]["speed"].append(float(speed))
                    except Exception:
                        pass
        elif isinstance(plasma[0], list):
            for row in plasma[1:]:
                if not row or len(row) < 3:
                    continue
                ts = str(row[0])
                if not ts.startswith("2026"):
                    continue
                blk = ts[:13].replace("T", " ") + ":00"
                try:
                    buckets[blk]["speed"].append(float(row[2]))
                except Exception:
                    pass

    if isinstance(mag, list) and mag:
        if isinstance(mag[0], dict):
            for row in mag:
                ts = str(row.get("time_tag") or row.get("time") or "")
                if not ts.startswith("2026"):
                    continue
                blk = ts[:13].replace("T", " ") + ":00"
                bz = row.get("bz_gsm", row.get("bz"))
                if bz is not None:
                    try:
                        buckets[blk]["bz"].append(float(bz))
                    except Exception:
                        pass
        elif isinstance(mag[0], list):
            for row in mag[1:]:
                if not row or len(row) < 4:
                    continue
                ts = str(row[0])
                if not ts.startswith("2026"):
                    continue
                blk = ts[:13].replace("T", " ") + ":00"
                try:
                    buckets[blk]["bz"].append(float(row[3]))
                except Exception:
                    pass

    rows = sorted(buckets.keys())
    log.info("hourly buckets=%s", len(rows))
    con = sqlite3.connect(args.db)
    before = con.execute("SELECT MAX(timestamp_blk), COUNT(*) FROM tbl_clima_espacial_raw").fetchone()
    log.info("before max=%s n=%s", before[0], before[1])
    n = 0
    for blk in rows:
        b = buckets[blk]
        bz, sp, kpv = b["bz"], b["speed"], b["kp"]
        vals = (
            blk,
            (sum(bz)/len(bz) if bz else None),
            0.0,
            (min(bz) if bz else None),
            (max(bz) if bz else None),
            (sum(sp)/len(sp) if sp else None),
            (max(sp) if sp else None),
            (max(kpv) if kpv else None),
            (sum(kpv)/len(kpv) if kpv else None),
            None,
        )
        if not args.dry_run:
            con.execute(
                "INSERT OR IGNORE INTO tbl_clima_espacial_raw "
                "(timestamp_blk, bz_promedio, bz_derivada, bz_min, bz_max, "
                "viento_solar_avg, viento_solar_max, kp_max, kp_promedio, proton_flux_10mev) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                vals,
            )
        n += 1
    if not args.dry_run:
        con.commit()
    after = con.execute("SELECT MAX(timestamp_blk), COUNT(*) FROM tbl_clima_espacial_raw").fetchone()
    n2026 = con.execute("SELECT COUNT(*) FROM tbl_clima_espacial_raw WHERE timestamp_blk LIKE '2026%'").fetchone()[0]
    sample = con.execute(
        "SELECT timestamp_blk, bz_promedio, kp_max, viento_solar_avg FROM tbl_clima_espacial_raw "
        "WHERE timestamp_blk LIKE '2026%' ORDER BY timestamp_blk DESC LIMIT 3"
    ).fetchall()
    con.close()
    log.info("wrote_attempts=%s after max=%s n=%s n2026=%s sample=%s", n, after[0], after[1], n2026, sample)

if __name__ == "__main__":
    main()
