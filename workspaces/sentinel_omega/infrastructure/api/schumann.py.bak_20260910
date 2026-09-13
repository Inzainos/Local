"""
Schumann Resonance connector — Tomsk Observatory (sosrff.tsu.ru).
Public spectrogram images, no authentication required.

Method: Computer vision (WPC — White Pixel Count) on HSV-filtered
spectrogram to estimate resonance excitation above the 7.83 Hz fundamental.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from sentinel_omega.infrastructure.api._http import get_session

logger = logging.getLogger(__name__)

TOMSK_URL = "http://sosrff.tsu.ru/new/shm.jpg"
TIMEOUT = 15
FUNDAMENTAL_HZ = 7.83
ROI_FRACTION = 0.4
HSV_LOWER = np.array([0, 0, 180])
HSV_UPPER = np.array([180, 60, 255])


def fetch_schumann_spectrogram(
    save_dir: Optional[str] = None,
) -> Optional[str]:
    """Download today's Schumann spectrogram from Tomsk Observatory."""
    try:
        resp = get_session().get(TOMSK_URL, timeout=TIMEOUT)
        resp.raise_for_status()

        if save_dir:
            path = Path(save_dir) / "tomsk_live.jpg"
        else:
            fd, path_str = tempfile.mkstemp(suffix=".jpg", prefix="tomsk_")
            import os
            os.close(fd)
            path = Path(path_str)

        path.write_bytes(resp.content)
        logger.info(f"Tomsk spectrogram downloaded: {path}")
        return str(path)
    except Exception as e:
        logger.error(f"Tomsk spectrogram download failed: {e}")
        return None


def analyze_spectrogram(image_path: str) -> Tuple[float, float]:
    """
    Analyze Tomsk spectrogram via WPC (White Pixel Count).

    Returns:
        (schumann_hz, activity_pct) — estimated frequency and activity percentage.
        Falls back to (7.83, 0.0) on any failure.
    """
    try:
        import cv2
    except ImportError:
        logger.warning("opencv-python not installed — returning baseline Schumann")
        return FUNDAMENTAL_HZ, 0.0

    if not image_path:
        return FUNDAMENTAL_HZ, 0.0

    try:
        img = cv2.imread(image_path)
        if img is None:
            logger.warning(f"Could not read image: {image_path}")
            return FUNDAMENTAL_HZ, 0.0

        h, w, _ = img.shape
        roi = img[0:int(h * ROI_FRACTION), 0:w]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)

        total_pixels = mask.size
        active_pixels = cv2.countNonZero(mask)
        activity_pct = round((active_pixels / total_pixels) * 100, 2)

        schumann_hz = round(FUNDAMENTAL_HZ + (activity_pct * 0.02), 2)

        logger.info(
            f"Schumann WPC: {schumann_hz} Hz, activity={activity_pct}%"
        )
        return schumann_hz, activity_pct
    except Exception as e:
        logger.error(f"Spectrogram analysis failed: {e}")
        return FUNDAMENTAL_HZ, 0.0


def fetch_schumann_resonance(
    save_dir: Optional[str] = None,
    cleanup: bool = True,
) -> Tuple[float, float]:
    """
    Full pipeline: download spectrogram → WPC analysis → return (hz, activity_pct).
    """
    import os

    path = fetch_schumann_spectrogram(save_dir=save_dir)
    if path is None:
        return FUNDAMENTAL_HZ, 0.0

    hz, pct = analyze_spectrogram(path)

    if cleanup and path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

    return hz, pct
