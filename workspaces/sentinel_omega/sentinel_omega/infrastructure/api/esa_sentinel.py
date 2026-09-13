"""
ESA Sentinel satellite connector via EODAG (Earth Observation Data Access Gateway).
Uses Copernicus Data Space Ecosystem for Sentinel-2 (multispectral) and Sentinel-1 (SAR).

Authentication: COPERNICUS_USER and COPERNICUS_PASSWORD environment variables.
Search is public; download requires credentials.

Products:
  - S2_MSI_L2A: Sentinel-2 Level-2A (multispectral, atmospherically corrected)
  - S1_SAR_GRD: Sentinel-1 SAR Ground Range Detected (deformation proxy)
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

PROVIDER = "cop_dataspace"


@dataclass
class SatelliteProduct:
    product_id: str
    title: str
    platform: str
    datetime_utc: str
    cloud_cover: Optional[float]
    geometry: Any
    download_link: Optional[str]
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SatelliteSearchResult:
    products: List[SatelliteProduct]
    total_found: int
    bbox: Tuple[float, float, float, float]
    date_range: Tuple[str, str]


def _get_dag():
    """Initialize EODAG with Copernicus credentials from environment."""
    from eodag import EODataAccessGateway

    dag = EODataAccessGateway()

    user = os.environ.get("COPERNICUS_USER", "")
    password = os.environ.get("COPERNICUS_PASSWORD", "")

    if user and password:
        dag.update_providers_config(f"""
            cop_dataspace:
                auth:
                    credentials:
                        username: {user}
                        password: {password}
        """)
        logger.info("Copernicus credentials configured from environment")
    else:
        logger.warning(
            "COPERNICUS_USER/COPERNICUS_PASSWORD not set — search works, download won't"
        )

    return dag


def search_sentinel2(
    bbox: Tuple[float, float, float, float],
    start: Optional[str] = None,
    end: Optional[str] = None,
    max_cloud_cover: float = 30.0,
    limit: int = 10,
) -> SatelliteSearchResult:
    """
    Search Sentinel-2 L2A imagery over a bounding box.

    Args:
        bbox: (lon_min, lat_min, lon_max, lat_max)
        start: ISO date string (default: 30 days ago)
        end: ISO date string (default: today)
        max_cloud_cover: maximum cloud cover percentage
        limit: max results to return
    """
    now = datetime.now(timezone.utc)
    if not start:
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end:
        end = now.strftime("%Y-%m-%d")

    geom = {
        "lonmin": bbox[0], "latmin": bbox[1],
        "lonmax": bbox[2], "latmax": bbox[3],
    }

    try:
        dag = _get_dag()
        results = dag.search(
            collection="S2_MSI_L2A",
            provider=PROVIDER,
            geom=geom,
            start=start,
            end=end,
            eo_cloud_cover=max_cloud_cover,
            limit=limit,
        )

        products = []
        for r in results:
            props = r.properties
            products.append(SatelliteProduct(
                product_id=props.get("id", ""),
                title=props.get("title", ""),
                platform=props.get("platform", ""),
                datetime_utc=props.get("datetime", ""),
                cloud_cover=props.get("eo:cloud_cover"),
                geometry=r.geometry,
                download_link=props.get("eodag:download_link"),
                properties=dict(props),
            ))

        logger.info(
            f"S2 search: {len(products)} products, "
            f"bbox={bbox}, dates={start}/{end}, cloud<{max_cloud_cover}%"
        )
        return SatelliteSearchResult(
            products=products,
            total_found=len(products),
            bbox=bbox,
            date_range=(start, end),
        )
    except Exception as e:
        logger.error(f"Sentinel-2 search failed: {e}")
        return SatelliteSearchResult(
            products=[], total_found=0,
            bbox=bbox, date_range=(start, end),
        )


def search_sentinel1_sar(
    bbox: Tuple[float, float, float, float],
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 10,
) -> SatelliteSearchResult:
    """
    Search Sentinel-1 SAR GRD imagery over a bounding box.
    SAR is not affected by cloud cover — works day/night, all weather.
    """
    now = datetime.now(timezone.utc)
    if not start:
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end:
        end = now.strftime("%Y-%m-%d")

    geom = {
        "lonmin": bbox[0], "latmin": bbox[1],
        "lonmax": bbox[2], "latmax": bbox[3],
    }

    try:
        dag = _get_dag()
        results = dag.search(
            collection="S1_SAR_GRD",
            provider=PROVIDER,
            geom=geom,
            start=start,
            end=end,
            limit=limit,
        )

        products = []
        for r in results:
            props = r.properties
            products.append(SatelliteProduct(
                product_id=props.get("id", ""),
                title=props.get("title", ""),
                platform=props.get("platform", ""),
                datetime_utc=props.get("datetime", ""),
                cloud_cover=None,
                geometry=r.geometry,
                download_link=props.get("eodag:download_link"),
                properties=dict(props),
            ))

        logger.info(f"S1 SAR search: {len(products)} products, bbox={bbox}")
        return SatelliteSearchResult(
            products=products,
            total_found=len(products),
            bbox=bbox,
            date_range=(start, end),
        )
    except Exception as e:
        logger.error(f"Sentinel-1 SAR search failed: {e}")
        return SatelliteSearchResult(
            products=[], total_found=0,
            bbox=bbox, date_range=(start, end),
        )


def compute_temporal_coverage(
    bbox: Tuple[float, float, float, float],
    days: int = 30,
) -> Dict[str, Any]:
    """
    Compute satellite revisit statistics for a region.
    Returns temporal density metrics useful for deformation monitoring.
    """
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    s2 = search_sentinel2(bbox, start, end, max_cloud_cover=50.0, limit=50)
    s1 = search_sentinel1_sar(bbox, start, end, limit=50)

    s2_dates = []
    for p in s2.products:
        if p.datetime_utc:
            try:
                dt = datetime.fromisoformat(p.datetime_utc.replace("Z", "+00:00"))
                s2_dates.append(dt)
            except ValueError:
                pass

    s1_dates = []
    for p in s1.products:
        if p.datetime_utc:
            try:
                dt = datetime.fromisoformat(p.datetime_utc.replace("Z", "+00:00"))
                s1_dates.append(dt)
            except ValueError:
                pass

    all_dates = sorted(s2_dates + s1_dates)
    revisit_days = []
    for i in range(1, len(all_dates)):
        delta = (all_dates[i] - all_dates[i - 1]).total_seconds() / 86400
        revisit_days.append(delta)

    return {
        "s2_count": len(s2.products),
        "s1_count": len(s1.products),
        "total_passes": len(all_dates),
        "mean_revisit_days": float(np.mean(revisit_days)) if revisit_days else 0.0,
        "min_revisit_days": float(np.min(revisit_days)) if revisit_days else 0.0,
        "max_revisit_days": float(np.max(revisit_days)) if revisit_days else 0.0,
        "s2_cloud_covers": [p.cloud_cover for p in s2.products if p.cloud_cover is not None],
        "bbox": bbox,
        "days_analyzed": days,
    }


def get_seismic_zone_bboxes() -> Dict[str, Tuple[float, float, float, float]]:
    """
    Pre-defined bounding boxes for key seismic monitoring zones.
    Aligned with dim_nodos_uvg from SENTINEL_OMEGA_PRO.db.
    """
    return {
        "guerrero_gap": (-100.5, 16.0, -98.5, 17.5),
        "oaxaca_costa": (-97.5, 15.5, -96.5, 16.5),
        "baja_falla": (-117.5, 32.0, -116.5, 33.0),
        "chiapas": (-93.5, 14.5, -92.0, 16.0),
        "jalisco_colima": (-104.5, 18.5, -103.5, 19.5),
        "michoacan": (-103.0, 17.5, -101.5, 18.5),
        "puebla_tlaxcala": (-98.5, 18.8, -97.8, 19.5),
        "ring_of_fire_japan": (139.0, 35.0, 141.0, 37.0),
        "ring_of_fire_chile": (-72.0, -34.0, -70.0, -32.0),
        "turkey_anatolia": (35.0, 37.0, 37.0, 39.0),
    }
