"""
OpenWeatherMap API connector — Atmospheric data for geodynamic analysis.

Fetches real-time weather for monitoring stations, mapping to fact_estado_tierra
schema: pressure, temperature, humidity, visibility, wind.

Legacy lineage: TITAN V32/V42 used OWM for Blue Jets pressure correlation
at Tlaxcala (19.31, -98.24). V2.0 extends to multiple seismic monitoring nodes.

Requires: OPENWEATHERMAP_KEY environment variable.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sentinel_omega.infrastructure.api._http import get_session

logger = logging.getLogger(__name__)

OWM_BASE = "https://api.openweathermap.org/data/2.5"
OWM_AIR_BASE = "https://api.openweathermap.org/data/2.5/air_pollution"
TIMEOUT = 10

MONITORING_STATIONS: Dict[str, Dict[str, float]] = {
    "tlaxcala": {"lat": 19.31, "lon": -98.24},
    "oaxaca": {"lat": 17.07, "lon": -96.72},
    "guerrero": {"lat": 17.55, "lon": -99.50},
    "colima": {"lat": 19.24, "lon": -103.72},
    "michoacan": {"lat": 19.17, "lon": -102.05},
    "chiapas": {"lat": 16.75, "lon": -93.12},
    "cdmx": {"lat": 19.43, "lon": -99.13},
    "puebla": {"lat": 19.04, "lon": -98.21},
}

# Global event nodes — key volcanic, tectonic, and marine points of the grid.
# Volcano/tectonic nodes are scanned for degassing (CO/SO2); marine nodes for
# thermal anomalies (the marine "variable fantasma": anomalous sea-surface
# heating linked to ionization/energy discharge, per the V601 lineage).
GLOBAL_EVENT_NODES: Dict[str, Dict[str, Any]] = {
    "popocatepetl": {"lat": 19.02, "lon": -98.62, "tipo": "VOLCAN"},
    "yellowstone": {"lat": 44.42, "lon": -110.58, "tipo": "VOLCAN"},
    "fuji": {"lat": 35.36, "lon": 138.72, "tipo": "TECTONICO"},
    "andes_chile": {"lat": -33.44, "lon": -70.66, "tipo": "TECTONICO"},
    "san_andres": {"lat": 34.05, "lon": -118.24, "tipo": "TECTONICO"},
    "guerrero_gap": {"lat": 16.85, "lon": -99.90, "tipo": "TECTONICO"},
    "islandia_rift": {"lat": 64.96, "lon": -19.02, "tipo": "TECTONICO"},
    "bermudas": {"lat": 25.00, "lon": -71.00, "tipo": "MARINO"},
    "hawaii_hotspot": {"lat": 19.89, "lon": -155.58, "tipo": "MARINO"},
    "fosa_japon": {"lat": 36.00, "lon": 142.00, "tipo": "MARINO"},
}

# Marine surface temp above this (deg C) counts as a thermal anomaly candidate.
MARINE_THERMAL_THRESHOLD_C = 29.0

# Reference stations in remote, unpopulated zones (open ocean, desert, polar).
# Human industrial/traffic emissions are effectively zero here, so any measured
# SO2/CO is natural background or true tectonic/volcanic outgassing. Used to
# learn the "clean baseline" — the signature of what natural degassing looks
# like against zero human noise, so populated-zone readings can be corrected.
REFERENCE_STATIONS: Dict[str, Dict[str, float]] = {
    "pacifico_nemo": {"lat": -48.87, "lon": -123.39},   # Point Nemo — most remote ocean point
    "atlantico_sur": {"lat": -30.0, "lon": -15.0},      # mid South Atlantic
    "indico_sur": {"lat": -40.0, "lon": 80.0},          # mid South Indian Ocean
    "atacama": {"lat": -24.5, "lon": -69.25},           # driest desert, minimal industry
    "antartida": {"lat": -75.0, "lon": 0.0},            # polar clean-air baseline
}


@dataclass
class AtmosphericReading:
    station: str
    lat: float
    lon: float
    pressure_hpa: float
    temp_c: float
    humidity_pct: float
    visibility_m: float
    wind_speed_ms: float
    wind_deg: float
    clouds_pct: float
    weather_id: int = 800


def _get_api_key() -> Optional[str]:
    key = os.environ.get("OPENWEATHERMAP_KEY")
    if not key:
        logger.warning("OPENWEATHERMAP_KEY not set")
    return key


def fetch_weather(
    lat: float,
    lon: float,
    station_name: str = "unknown",
) -> Optional[AtmosphericReading]:
    """Fetch current weather for a single coordinate."""
    api_key = _get_api_key()
    if not api_key:
        return None

    url = f"{OWM_BASE}/weather"
    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
    }
    try:
        resp = get_session().get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        main = data.get("main", {})
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        weather_list = data.get("weather", [])
        weather_id = weather_list[0].get("id", 800) if weather_list else 800

        reading = AtmosphericReading(
            station=station_name,
            lat=lat,
            lon=lon,
            pressure_hpa=main.get("pressure", 1013.0),
            temp_c=main.get("temp", 20.0),
            humidity_pct=main.get("humidity", 50.0),
            visibility_m=data.get("visibility", 10000),
            wind_speed_ms=wind.get("speed", 0.0),
            wind_deg=wind.get("deg", 0.0),
            clouds_pct=clouds.get("all", 0),
            weather_id=weather_id,
        )
        logger.info(
            f"OWM {station_name}: {reading.pressure_hpa}hPa, "
            f"{reading.temp_c}C, {reading.humidity_pct}%RH"
        )
        return reading
    except Exception as e:
        logger.error(f"OWM fetch failed for {station_name}: {e}")
        return None


def fetch_air_quality(
    lat: float,
    lon: float,
) -> Optional[Dict[str, float]]:
    """Fetch air pollution data (CO, SO2, NO2, PM2.5) for a coordinate."""
    api_key = _get_api_key()
    if not api_key:
        return None

    params = {
        "lat": lat,
        "lon": lon,
        "appid": api_key,
    }
    try:
        resp = get_session().get(OWM_AIR_BASE, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("list"):
            return None

        components = data["list"][0].get("components", {})
        result = {
            "co": components.get("co", 0.0),
            "so2": components.get("so2", 0.0),
            "no2": components.get("no2", 0.0),
            "pm2_5": components.get("pm2_5", 0.0),
            "pm10": components.get("pm10", 0.0),
            "o3": components.get("o3", 0.0),
            "aqi": data["list"][0].get("main", {}).get("aqi", 0),
        }
        logger.info(f"OWM AQ: CO={result['co']}, SO2={result['so2']}, AQI={result['aqi']}")
        return result
    except Exception as e:
        logger.error(f"OWM air quality fetch failed: {e}")
        return None


def fetch_reference_baseline() -> Optional[Dict[str, float]]:
    """
    Learn the natural degassing signature from remote, unpopulated zones.

    Averages air-quality gases across ocean/desert/polar reference stations
    where human emissions are ~zero. The result is the "clean background" —
    what the atmosphere looks like with only natural degassing present.
    Populated-zone readings are then compared against this to isolate the
    true tectonic/volcanic outgassing from urban pollution noise.
    """
    samples: List[Dict[str, float]] = []
    for name, coords in REFERENCE_STATIONS.items():
        aq = fetch_air_quality(coords["lat"], coords["lon"])
        if aq:
            samples.append(aq)

    if not samples:
        return None

    gases = ("co", "so2", "no2", "pm2_5", "pm10", "o3")
    baseline = {
        g: round(sum(s.get(g, 0.0) for s in samples) / len(samples), 3)
        for g in gases
    }
    baseline["station_count"] = len(samples)
    logger.info(
        f"Reference baseline (natural degassing): "
        f"SO2={baseline['so2']}, CO={baseline['co']} from {len(samples)} clean zones"
    )
    return baseline


def scan_global_nodes(
    nodes: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Scan the global event nodes for degassing and marine thermal anomalies.

    For each node fetches gases (CO/SO2/NO2) and surface temperature.
    Volcano/tectonic nodes carry the degassing reading; marine nodes carry
    the sea-surface temperature for thermal-anomaly analysis in Beta-2.
    """
    target = nodes or list(GLOBAL_EVENT_NODES.keys())
    results: List[Dict[str, Any]] = []

    for name in target:
        cfg = GLOBAL_EVENT_NODES.get(name)
        if cfg is None:
            continue

        entry: Dict[str, Any] = {
            "node": name,
            "lat": cfg["lat"],
            "lon": cfg["lon"],
            "tipo": cfg["tipo"],
        }

        aq = fetch_air_quality(cfg["lat"], cfg["lon"])
        if aq:
            entry["so2"] = aq.get("so2", 0.0)
            entry["co"] = aq.get("co", 0.0)
            entry["no2"] = aq.get("no2", 0.0)

        reading = fetch_weather(cfg["lat"], cfg["lon"], station_name=name)
        if reading:
            entry["temp_c"] = reading.temp_c
            entry["pressure_hpa"] = reading.pressure_hpa

        if "so2" in entry or "temp_c" in entry:
            results.append(entry)

    logger.info(f"Global node scan: {len(results)}/{len(target)} nodes responding")
    return results


def fetch_monitoring_network(
    stations: Optional[List[str]] = None,
) -> List[AtmosphericReading]:
    """Fetch weather for multiple monitoring stations."""
    target = stations or list(MONITORING_STATIONS.keys())
    readings = []
    for name in target:
        coords = MONITORING_STATIONS.get(name)
        if coords is None:
            continue
        reading = fetch_weather(coords["lat"], coords["lon"], station_name=name)
        if reading:
            readings.append(reading)
    logger.info(f"Monitoring network: {len(readings)}/{len(target)} stations responding")
    return readings


def compute_pressure_gradient(readings: List[AtmosphericReading]) -> Dict[str, Any]:
    """Compute pressure anomalies across the monitoring network."""
    if len(readings) < 2:
        return {"mean_pressure": 1013.0, "pressure_spread": 0.0, "low_pressure_stations": []}

    pressures = [r.pressure_hpa for r in readings]
    mean_p = sum(pressures) / len(pressures)
    spread = max(pressures) - min(pressures)

    low_stations = [
        r.station for r in readings
        if r.pressure_hpa < 1008
    ]

    return {
        "mean_pressure": mean_p,
        "pressure_spread": spread,
        "low_pressure_stations": low_stations,
        "station_count": len(readings),
    }
