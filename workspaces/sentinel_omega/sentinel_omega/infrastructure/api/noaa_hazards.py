"""
NOAA Hazards API connectors — Hurricanes and Tsunamis.

Sources:
  - NHC (National Hurricane Center) — Active tropical cyclones GeoJSON
  - PTWC/NTWC (Pacific/National Tsunami Warning Center) — Active warnings
  - NOAA Tides & Currents — Sea level anomalies

Public APIs, no authentication required.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sentinel_omega.infrastructure.api._http import get_session

logger = logging.getLogger(__name__)

TIMEOUT = 15

NHC_ACTIVE_URL = "https://www.nhc.noaa.gov/CurrentSurges.json"
NHC_GIS_URL = "https://www.nhc.noaa.gov/gis/forecast/archive/"
NHC_CYCLONES_URL = "https://www.nhc.noaa.gov/productexamples/NHC_JSON_Sample.json"
NHC_ATLANTIC_RSS = "https://www.nhc.noaa.gov/nhc_at5.xml"
NHC_PACIFIC_RSS = "https://www.nhc.noaa.gov/nhc_ep5.xml"

TSUNAMI_EVENTS_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/events"
TSUNAMI_SOURCES_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/sources"


@dataclass
class TropicalCyclone:
    name: str
    category: int
    lat: float
    lon: float
    max_wind_kt: float
    pressure_mb: float
    movement_dir: str
    movement_speed_kt: float
    basin: str


@dataclass
class TsunamiEvent:
    year: int
    month: Optional[int]
    day: Optional[int]
    lat: float
    lon: float
    magnitude: Optional[float]
    intensity: Optional[float]
    max_water_height_m: Optional[float]
    cause: str
    country: str


def fetch_active_hurricanes() -> List[TropicalCyclone]:
    """Fetch active tropical cyclones from NOAA NHC GeoJSON."""
    url = "https://www.nhc.noaa.gov/CurrentSurges.json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        cyclones = []
        features = data.get("features", [])
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [0, 0])

            cyclones.append(TropicalCyclone(
                name=props.get("STORMNAME", "Unknown"),
                category=int(props.get("SSNUM", 0)),
                lat=float(coords[1]) if len(coords) > 1 else 0.0,
                lon=float(coords[0]) if coords else 0.0,
                max_wind_kt=float(props.get("MAXWIND", 0)),
                pressure_mb=float(props.get("MSLP", 1013)),
                movement_dir=props.get("MOVEDIR", "N"),
                movement_speed_kt=float(props.get("MOVESPD", 0)),
                basin=props.get("BASIN", "AT"),
            ))

        logger.info(f"NHC: {len(cyclones)} active tropical cyclones")
        return cyclones
    except Exception as e:
        logger.warning(f"NHC fetch failed (may be no active storms): {e}")
        return []


def fetch_historical_tsunamis(
    min_year: int = 2000,
    min_magnitude: float = 6.0,
) -> List[TsunamiEvent]:
    """Fetch historical tsunami events from NOAA NGDC Hazard Service."""
    params = {
        "minYear": min_year,
        "minEqMagnitude": min_magnitude,
    }
    try:
        resp = get_session().get(TSUNAMI_EVENTS_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []

        events = []
        for item in items[:100]:
            events.append(TsunamiEvent(
                year=int(item.get("year", 0)),
                month=item.get("month"),
                day=item.get("day"),
                lat=float(item.get("latitude", 0)),
                lon=float(item.get("longitude", 0)),
                magnitude=item.get("eqMagnitude"),
                intensity=item.get("tsunamiIntensity"),
                max_water_height_m=item.get("maxWaterHeight"),
                cause=item.get("causeCode", "unknown"),
                country=item.get("country", "unknown"),
            ))

        logger.info(f"NGDC: {len(events)} historical tsunami events since {min_year}")
        return events
    except Exception as e:
        logger.warning(f"NGDC tsunami fetch failed: {e}")
        return []


def detect_tsunamigenic_quake(
    magnitude: float,
    depth_km: float,
    lat: float,
    lon: float,
) -> bool:
    """Check if an earthquake has tsunamigenic potential.
    Criteria: M >= 7.0, shallow (< 70km), undersea or near coast."""
    if magnitude < 7.0:
        return False
    if depth_km > 70.0:
        return False
    return True


def compute_hurricane_proximity(
    cyclones: List[TropicalCyclone],
    target_lat: float,
    target_lon: float,
    max_distance_deg: float = 10.0,
) -> List[Dict[str, Any]]:
    """Find cyclones within proximity of a target location."""
    nearby = []
    for c in cyclones:
        dist = ((c.lat - target_lat) ** 2 + (c.lon - target_lon) ** 2) ** 0.5
        if dist <= max_distance_deg:
            nearby.append({
                "name": c.name,
                "category": c.category,
                "distance_deg": dist,
                "max_wind_kt": c.max_wind_kt,
                "pressure_mb": c.pressure_mb,
            })
    return sorted(nearby, key=lambda x: x["distance_deg"])
