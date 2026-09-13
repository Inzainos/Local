"""
USGS Earthquake API connector.
Public FDSN web service, no authentication.
"""

import logging
from typing import Optional

import pandas as pd
from sentinel_omega.infrastructure.api._http import get_session
from sentinel_omega.infrastructure.api.circuit_breaker import circuit

logger = logging.getLogger(__name__)

TIMEOUT = 15


@circuit("usgs")
def fetch_earthquakes(
    min_magnitude: float = 4.5,
    days: int = 30,
    max_results: int = 500,
) -> Optional[pd.DataFrame]:
    """Fetch recent earthquakes from USGS FDSN."""
    from datetime import datetime, timedelta, timezone

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)

    _fdsn_fmt = "%Y-%m-%dT%H:%M:%S"
    starttime = start.strftime(_fdsn_fmt)
    endtime = end.strftime(_fdsn_fmt)

    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query"
        f"?format=geojson&starttime={starttime}"
        f"&endtime={endtime}"
        f"&minmagnitude={min_magnitude}&limit={max_results}"
        "&orderby=time"
    )
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        features = resp.json().get("features", [])

        records = []
        for f in features:
            props = f.get("properties", {})
            coords = f.get("geometry", {}).get("coordinates", [None, None, None])
            event_id = f.get("id") or props.get("code") or props.get("ids")
            if isinstance(event_id, str) and event_id.startswith(","):
                event_id = event_id.strip(",").split(",")[0]
            records.append({
                "event_id": event_id or None,
                "time": pd.to_datetime(props.get("time"), unit="ms"),
                "magnitude": props.get("mag"),
                "place": props.get("place"),
                "depth_km": coords[2] if len(coords) > 2 else None,
                "longitude": coords[0] if len(coords) > 0 else None,
                "latitude": coords[1] if len(coords) > 1 else None,
                "type": props.get("type"),
                "mag_type": props.get("magType") or "",
            })

        df = pd.DataFrame(records)
        logger.info(f"USGS: {len(df)} earthquakes (M>={min_magnitude}, {days}d)")
        return df.sort_values("time")
    except Exception as e:
        logger.error(f"USGS fetch failed: {e}")
    return None
