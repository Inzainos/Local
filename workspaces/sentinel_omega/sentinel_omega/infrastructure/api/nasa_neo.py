"""
NASA NEO (Near-Earth Objects) API connector — External gravity trigger.

Potentially hazardous asteroids passing close to Earth are treated as an
external gravitational modulator, in the same family as the lunar trigger:
not an energy source, but a possible "when" for nodes already critical.

Requires: NASA_API_KEY environment variable (falls back to DEMO_KEY,
which is rate-limited but functional).
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sentinel_omega.infrastructure.api._http import get_session
from sentinel_omega.infrastructure.api.circuit_breaker import circuit

logger = logging.getLogger(__name__)

NEO_FEED_URL = "https://api.nasa.gov/neo/rest/v1/feed"
TIMEOUT = 15


@circuit("nasa_neo")
def fetch_neo_hazard_summary(date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch today's near-Earth objects and summarize the hazardous ones.

    Returns counts plus the closest hazardous approach in lunar distances (LD),
    or None if the API is unreachable.
    """
    api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")
    day = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    params = {"start_date": day, "end_date": day, "api_key": api_key}

    try:
        resp = get_session().get(NEO_FEED_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        objects = data.get("near_earth_objects", {}).get(day, [])
        hazardous = [o for o in objects if o.get("is_potentially_hazardous_asteroid")]

        closest_ld = None
        closest_name = ""
        for o in hazardous:
            for approach in o.get("close_approach_data", []):
                try:
                    ld = float(approach["miss_distance"]["lunar"])
                except (KeyError, TypeError, ValueError):
                    continue
                if closest_ld is None or ld < closest_ld:
                    closest_ld = ld
                    closest_name = o.get("name", "")

        result = {
            "total_count": len(objects),
            "hazardous_count": len(hazardous),
            "closest_hazardous_ld": closest_ld,
            "closest_hazardous_name": closest_name,
            "date": day,
        }
        logger.info(
            f"NEO feed: {result['total_count']} objects, "
            f"{result['hazardous_count']} hazardous"
            + (f", closest {closest_ld:.1f} LD" if closest_ld is not None else "")
        )
        return result
    except Exception as e:
        logger.error(f"NASA NEO fetch failed: {e}")
        return None
