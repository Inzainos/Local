"""
GFZ Potsdam Kp connector — long-history geomagnetic index.

NOAA SWPC only serves a short recent window of Kp (~1-7 days). For correlation
analysis over months (Júpiter), the GFZ Potsdam Kp web service provides the full
historical 3-hourly Kp series. Public, no key. Data © GFZ Potsdam, CC BY 4.0.

Returns the same shape as noaa.fetch_kp_index — DataFrame['time_tag','kp_index'] —
so it is a drop-in long-history source. Degrades to None on any failure.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

GFZ_URL = "https://kp.gfz.de/app/json/"
TIMEOUT = 30


def fetch_kp_history(days: int = 90) -> Optional[pd.DataFrame]:
    """Fetch the 3-hourly Kp index for the last `days` days from GFZ Potsdam."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "start": start.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end.strftime("%Y-%m-%dT23:59:59Z"),
        "index": "Kp",
    }
    try:
        resp = requests.get(GFZ_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        kp = data.get("Kp")
        dt = data.get("datetime")
        if not kp or not dt or len(kp) != len(dt):
            logger.warning("GFZ Kp: empty or malformed response")
            return None
        df = pd.DataFrame({"time_tag": pd.to_datetime(dt), "kp_index": pd.to_numeric(kp, errors="coerce")})
        df = df.dropna(subset=["kp_index"]).sort_values("time_tag")
        logger.info(f"Fetched {len(df)} GFZ Kp records over {days} days")
        return df
    except Exception as e:  # noqa: BLE001 — degrade cleanly
        logger.error(f"GFZ Kp fetch failed: {e}")
        return None
