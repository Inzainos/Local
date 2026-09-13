"""
Schumann Resonance connector — Tomsk Observatory (sosrff.tsu.ru).
Public spectrogram images, no authentication required.

Method: Computer vision (WPC — White Pixel Count) on HSV-filtered
spectrogram to estimate resonance excitation above the 7.83 Hz fundamental.

IMPORTANT (2026-09-10 ingest fix):
  - Tomsk HTTP redirects to HTTPS with an *expired* certificate. We must
    fetch with verify=False for sosrff.tsu.ru only, otherwise every cycle
    silently falls back to (7.83, 0.0) and poisons tbl_schumann_vivo.
  - On any failure we return None (not a fake baseline) so callers can skip
    INSERT / mark LOCF instead of writing synthetic zeros.
"""

from __future__ import annotations

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
    """Download today's Schumann spectrogram from Tomsk Observatory.

    Uses verify=False because sosrff.tsu.ru presents an expired TLS cert
    after the HTTP→HTTPS redirect (confirmed 2026-09-10).
    """
    try:
        resp = get_session().get(TOMSK_URL, timeout=TIMEOUT, verify=False)
        resp.raise_for_status()

        if save_dir:
            path = Path(save_dir) / "tomsk_live.jpg"
        else:
            fd, path_str = tempfile.mkstemp(suffix=".jpg", prefix="tomsk_")
            import os
            os.close(fd)
            path = Path(path_str)

        path.write_bytes(resp.content)
        logger.info(f"Tomsk spectrogram downloaded: {path} ({len(resp.content)} bytes)")
        return str(path)
    except Exception as e:
        logger.error(f"Tomsk spectrogram download failed: {e}")
        return None


def analyze_spectrogram(image_path: str) -> Optional[Tuple[float, float]]:
    """
    Analyze Tomsk spectrogram via WPC (White Pixel Count).

    Returns:
        (schumann_hz, activity_pct) or None on failure / missing opencv.
    """
    try:
        import cv2
    except ImportError:
        logger.error(
            "opencv-python not installed — cannot analyze Schumann spectrogram. "
            "Install: pip install opencv-python-headless"
        )
        return None

    if not image_path:
        return None

    try:
        img = cv2.imread(image_path)
        if img is None:
            logger.warning(f"Could not read image: {image_path}")
            return None

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
        return None


def is_baseline_placeholder(hz: Optional[float], activity: Optional[float]) -> bool:
    """True when values look like the historical fake fallback (7.83, 0.0)."""
    if hz is None or activity is None:
        return True
    try:
        return abs(float(hz) - FUNDAMENTAL_HZ) < 1e-9 and float(activity) == 0.0
    except (TypeError, ValueError):
        return True


def fetch_schumann_resonance(
    save_dir: Optional[str] = None,
    cleanup: bool = True,
) -> Optional[Tuple[float, float]]:
    """
    Full pipeline: download spectrogram → WPC analysis → (hz, activity_pct).

    Returns None on any failure (network, SSL, missing cv2, bad image).
    Callers MUST NOT invent 7.83/0.0; skip persist or use LOCF instead.
    """
    import os
    import urllib3

    # Tomsk cert is expired; silence the single-host InsecureRequestWarning noise.
    try:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

    path = fetch_schumann_spectrogram(save_dir=save_dir)
    if path is None:
        return None

    result = analyze_spectrogram(path)

    if cleanup and path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass

    if result is None:
        return None

    hz, pct = result
    if is_baseline_placeholder(hz, pct):
        # Extremely quiet spectrogram is possible but indistinguishable from
        # the old fake fallback; treat as no-signal so we do not keep writing
        # identical placeholder rows every hour.
        logger.warning(
            "Schumann WPC returned baseline placeholder (7.83, 0.0) — "
            "treating as no-signal (skip persist)"
        )
        return None

    return hz, pct
