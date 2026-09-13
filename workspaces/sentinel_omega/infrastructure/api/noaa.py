"""
NOAA SWPC API connector — Geodynamic data.
Public API, no authentication required.

Sources:
  - Kp index (planetary magnetic index)
  - GOES X-ray flux (solar flares)
  - Solar wind (plasma speed, density)
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from sentinel_omega.infrastructure.api._http import get_session
from sentinel_omega.infrastructure.api.circuit_breaker import circuit

logger = logging.getLogger(__name__)

NOAA_BASE = "https://services.swpc.noaa.gov/json/"
TIMEOUT = 15


@circuit("noaa")
def fetch_kp_index(days: int = 30) -> Optional[pd.DataFrame]:
    """Fetch Kp index from NOAA SWPC."""
    url = f"{NOAA_BASE}planetary_k_index_1m.json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        if "kp_index" in df.columns and "time_tag" in df.columns:
            df["time_tag"] = pd.to_datetime(df["time_tag"])
            df["kp_index"] = pd.to_numeric(df["kp_index"], errors="coerce")
            df = df.dropna(subset=["kp_index"])
            logger.info(f"Fetched {len(df)} Kp records from NOAA")
            return df[["time_tag", "kp_index"]].sort_values("time_tag")
    except Exception as e:
        logger.error(f"NOAA Kp fetch failed: {e}")
    return None


@circuit("noaa")
def fetch_goes_xray() -> Optional[pd.DataFrame]:
    """Fetch GOES X-ray flux (7-day, 0.1-0.8nm band) for solar flare analysis."""
    url = "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        if "time_tag" in df.columns and "flux" in df.columns:
            df["time_tag"] = pd.to_datetime(df["time_tag"])
            df["flux"] = pd.to_numeric(df["flux"], errors="coerce")
            logger.info(f"Fetched {len(df)} GOES X-ray records")
            return df[["time_tag", "flux", "energy"]].sort_values("time_tag")
    except Exception as e:
        logger.error(f"GOES X-ray fetch failed: {e}")
    return None


@circuit("noaa")
def fetch_electron_flux() -> Optional[pd.DataFrame]:
    """Fetch GOES integral electron flux (relativistic electrons, 6-hour).

    High electron flux marks magnetospheric energization — a charge-loading
    signal complementary to proton flux in the risk composite.
    """
    url = "https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-6-hour.json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        if "time_tag" in df.columns and "flux" in df.columns:
            df["time_tag"] = pd.to_datetime(df["time_tag"])
            df["flux"] = pd.to_numeric(df["flux"], errors="coerce")
            df = df.dropna(subset=["flux"])
            logger.info(f"Fetched {len(df)} GOES electron flux records")
            return df[["time_tag", "flux"]].sort_values("time_tag")
    except Exception as e:
        logger.error(f"GOES electron flux fetch failed: {e}")
    return None


@circuit("noaa")
def fetch_solar_wind() -> Optional[pd.DataFrame]:
    """Fetch real-time solar wind data (Bz, speed, density)."""
    url = f"{NOAA_BASE}rtsw/rtsw_wind_1m.json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        cols = ["time_tag", "proton_speed", "proton_density"]
        available = [c for c in cols if c in df.columns]
        if available:
            df["time_tag"] = pd.to_datetime(df["time_tag"])
            for c in available[1:]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            logger.info(f"Fetched {len(df)} solar wind records")
            return df[available].sort_values("time_tag")
    except Exception as e:
        logger.error(f"Solar wind fetch failed: {e}")
    return None


@circuit("noaa")
def fetch_mag_field() -> Optional[pd.DataFrame]:
    """Fetch real-time magnetometer data (Bz GSM component)."""
    url = f"{NOAA_BASE}rtsw/rtsw_mag_1m.json"
    try:
        resp = get_session().get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        if "time_tag" in df.columns and "bz_gsm" in df.columns:
            df["time_tag"] = pd.to_datetime(df["time_tag"])
            df["bz_gsm"] = pd.to_numeric(df["bz_gsm"], errors="coerce")
            logger.info(f"Fetched {len(df)} Bz records")
            return df[["time_tag", "bz_gsm"]].sort_values("time_tag")
    except Exception as e:
        logger.error(f"Magnetometer fetch failed: {e}")
    return None
