"""
Geophysical data connector — IERS LOD and Lunar ephemeris.
All public data, no authentication required.

Sources:
  - IERS Bulletin A (Length of Day excess, UT1-UTC)
  - PyEphem (Lunar phase computation)
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np
import pandas as pd
from sentinel_omega.infrastructure.api._http import get_session

logger = logging.getLogger(__name__)

IERS_FINALS_URL = (
    "https://datacenter.iers.org/data/csv/finals2000A.daily.csv"
)
TIMEOUT = 20


def fetch_lod_series(days: int = 90) -> Optional[pd.DataFrame]:
    """
    Fetch Length-of-Day excess (LOD) from IERS Bulletin A finals data.
    LOD is the deviation of day length from 86400 SI seconds (in ms).
    """
    try:
        resp = get_session().get(IERS_FINALS_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        lines = resp.text.strip().split("\n")
        if len(lines) < 2:
            logger.warning("IERS response too short")
            return None

        header = lines[0].split(";")
        col_map = {h.strip(): i for i, h in enumerate(header)}

        mjd_col = None
        lod_col = None
        for key in col_map:
            if "MJD" in key.upper():
                mjd_col = col_map[key]
            if "LOD" in key.upper() and "SIGMA" not in key.upper():
                lod_col = col_map[key]

        if mjd_col is None or lod_col is None:
            logger.warning(f"IERS columns not found: {list(col_map.keys())}")
            return None

        records = []
        for line in lines[1:]:
            parts = line.split(";")
            if len(parts) <= max(mjd_col, lod_col):
                continue
            try:
                mjd = float(parts[mjd_col].strip())
                lod_str = parts[lod_col].strip()
                if not lod_str:
                    continue
                lod = float(lod_str)
                records.append({"mjd": mjd, "lod_ms": lod})
            except (ValueError, IndexError):
                continue

        if not records:
            logger.warning("No valid LOD records parsed from IERS")
            return None

        df = pd.DataFrame(records)
        df["date"] = pd.to_datetime(df["mjd"] + 2400000.5, unit="D", origin="julian")
        df = df.sort_values("date").tail(days).reset_index(drop=True)
        logger.info(f"Fetched {len(df)} LOD records from IERS")
        return df[["date", "lod_ms"]]

    except Exception as e:
        logger.error(f"IERS LOD fetch failed: {e}")
        return None


def compute_lunar_phase(date: Optional[datetime] = None) -> Dict[str, float]:
    """
    Compute current lunar phase using PyEphem.
    Returns phase fraction (0=new, 0.5=full, 1=new again) and illumination %.
    """
    try:
        import ephem
    except ImportError:
        logger.warning("ephem not installed — returning default lunar phase")
        return {"phase_fraction": 0.5, "illumination_pct": 50.0, "phase_angle_deg": 180.0}

    if date is None:
        date = datetime.now(timezone.utc)

    moon = ephem.Moon(date)
    phase_pct = moon.phase
    illumination = phase_pct

    next_new = ephem.next_new_moon(date)
    prev_new = ephem.previous_new_moon(date)
    cycle_length = float(next_new - prev_new)
    days_since_new = float(ephem.Date(date) - prev_new)
    phase_fraction = days_since_new / cycle_length if cycle_length > 0 else 0.5

    phase_angle = phase_fraction * 360.0

    logger.info(
        f"Lunar phase: {phase_fraction:.3f} (illum={illumination:.1f}%, "
        f"angle={phase_angle:.1f}°)"
    )
    return {
        "phase_fraction": round(phase_fraction, 4),
        "illumination_pct": round(illumination, 2),
        "phase_angle_deg": round(phase_angle, 2),
    }


def compute_lunar_phase_series(days: int = 30) -> np.ndarray:
    """
    Compute lunar phase fraction for the past N days.
    Returns array of phase fractions (0-1).
    """
    try:
        import ephem
    except ImportError:
        return np.full(days, 0.5)

    from datetime import timedelta

    now = datetime.now(timezone.utc)
    phases = []
    for d in range(days, 0, -1):
        target = now - timedelta(days=d)
        next_new = ephem.next_new_moon(target)
        prev_new = ephem.previous_new_moon(target)
        cycle = float(next_new - prev_new)
        elapsed = float(ephem.Date(target) - prev_new)
        phases.append(elapsed / cycle if cycle > 0 else 0.5)

    return np.array(phases)
