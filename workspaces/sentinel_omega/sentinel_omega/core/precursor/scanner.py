"""
Precursor Scanner — Runs all detection functions against live pipeline data.

On each geodynamic cycle, the scanner evaluates atmospheric readings,
Kp series, seismic catalogs, SO2/air quality, NOAA space weather,
NHC hurricane data, and financial signals to detect active precursors
across all 15 categories.

Each detected precursor is returned as a PrecursorDetection with its
type, source station/region, confidence, and raw values.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from sentinel_omega.core.precursor.precursor_types import (
    PrecursorType,
    PRECURSOR_DISPLAY_NAMES,
    PRECURSOR_PROFILES,
    detect_blue_jet,
    detect_niebla_tule,
    detect_silent_trigger,
    detect_seismic_cluster,
    detect_volcanic_precursor,
    detect_sprite_rojo,
    detect_hurricane_proximity,
    detect_tsunami_potential,
    compute_precipitacion_potencial,
    detect_precipitacion_potencial,
)

logger = logging.getLogger(__name__)

# Precipitation scanner confidence thresholds
_PREC_HUMIDITY_HIGH = 80.0
_PREC_CLOUDS_HIGH = 70.0
_PREC_PI_VERY_HIGH = 45.0
_PREC_CONF_BASE = 0.50
_PREC_CONF_HUMIDITY_BOOST = 0.15
_PREC_CONF_CLOUDS_BOOST = 0.10
_PREC_CONF_PI_BOOST = 0.10


@dataclass
class PrecursorDetection:
    tipo: PrecursorType
    display_name: str
    station: str
    lat: Optional[float]
    lon: Optional[float]
    confidence: float
    values: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class PrecursorScanner:

    def __init__(self):
        self.last_detections: List[PrecursorDetection] = []

    def scan(
        self,
        alfa1_data: Dict[str, Any],
        beta1_data: Dict[str, Any],
        delta_data: Dict[str, Any],
        hurricane_data: Optional[Dict[str, Any]] = None,
        financial_data: Optional[Dict[str, Any]] = None,
    ) -> List[PrecursorDetection]:
        detections: List[PrecursorDetection] = []

        atmospheric = delta_data.get("atmospheric_readings", [])
        air_quality = delta_data.get("air_quality", {})
        kp_series = beta1_data.get("kp_series")
        seismic_mags = beta1_data.get("seismic_magnitudes")
        schumann_hz = beta1_data.get("schumann_frequency")
        schumann_pct = beta1_data.get("schumann_activity", 0.0)

        omni_df = alfa1_data.get("omni_dataframe")
        bz = 0.0
        viento = 0.0
        if omni_df is not None:
            if "bz_gsm" in omni_df.columns:
                bz = float(np.nanmean(omni_df["bz_gsm"]))
            if "plasma_speed" in omni_df.columns:
                viento = float(np.nanmean(omni_df["plasma_speed"]))

        kp_mean = 0.0
        if kp_series is not None and len(kp_series) > 0:
            kp_mean = float(np.nanmean(kp_series))

        detections.extend(self._scan_blue_jets(atmospheric))
        detections.extend(self._scan_sprites_rojos(atmospheric))
        detections.extend(self._scan_niebla_tule(atmospheric))
        detections.extend(self._scan_silent_trigger(kp_series))
        detections.extend(self._scan_seismic_cluster(seismic_mags))
        detections.extend(self._scan_volcanic(air_quality, seismic_mags, atmospheric))
        detections.extend(self._scan_schumann(schumann_hz, schumann_pct))
        detections.extend(self._scan_tormenta_solar(bz, kp_mean, viento))
        detections.extend(self._scan_perturbacion_geomagnetica(bz, kp_mean))
        detections.extend(self._scan_tsunami(seismic_mags, delta_data))
        detections.extend(self._scan_hurricanes(hurricane_data or {}))
        detections.extend(self._scan_financial_correlation(financial_data or {}))
        detections.extend(self._scan_precipitacion(atmospheric, schumann_hz))

        self.last_detections = detections
        if detections:
            logger.warning(
                f"PRECURSOR SCAN: {len(detections)} active — "
                f"{[d.tipo.value for d in detections]}"
            )
        else:
            logger.info("Precursor scan: no active precursors")

        return detections

    def _scan_blue_jets(
        self, atmospheric: List[Dict[str, Any]]
    ) -> List[PrecursorDetection]:
        results = []
        for reading in atmospheric:
            temp_c = reading.get("temp_c", 20.0)
            weather_id = reading.get("weather_id", 800)
            pressure = reading.get("pressure_hpa", 1013.0)

            if detect_blue_jet(temp_c, weather_id, pressure):
                confidence = 0.7
                if pressure < 1008:
                    confidence += 0.1
                if temp_c > 30:
                    confidence += 0.1

                results.append(PrecursorDetection(
                    tipo=PrecursorType.BLUE_JET,
                    display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.BLUE_JET],
                    station=reading.get("station", "unknown"),
                    lat=reading.get("lat"),
                    lon=reading.get("lon"),
                    confidence=min(confidence, 0.95),
                    values={
                        "temp_c": temp_c,
                        "weather_id": weather_id,
                        "pressure_hpa": pressure,
                    },
                ))
        return results

    def _scan_niebla_tule(
        self, atmospheric: List[Dict[str, Any]]
    ) -> List[PrecursorDetection]:
        results = []
        for reading in atmospheric:
            humidity = reading.get("humidity_pct", 50.0)
            visibility = reading.get("visibility_m", 10000)

            if detect_niebla_tule(humidity, visibility):
                confidence = 0.6
                if visibility < 500:
                    confidence += 0.15
                if humidity > 95:
                    confidence += 0.1

                results.append(PrecursorDetection(
                    tipo=PrecursorType.NIEBLA_TULE,
                    display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.NIEBLA_TULE],
                    station=reading.get("station", "unknown"),
                    lat=reading.get("lat"),
                    lon=reading.get("lon"),
                    confidence=min(confidence, 0.95),
                    values={
                        "humidity_pct": humidity,
                        "visibility_m": visibility,
                    },
                ))
        return results

    def _scan_silent_trigger(
        self, kp_series: Optional[Any]
    ) -> List[PrecursorDetection]:
        if kp_series is None or len(kp_series) < 12:
            return []

        kp_list = list(kp_series[-24:]) if len(kp_series) > 24 else list(kp_series)
        if not detect_silent_trigger(kp_list):
            return []

        kp_mean = sum(kp_list) / len(kp_list)
        confidence = 0.65
        if len(kp_list) >= 24:
            confidence += 0.15
        if kp_mean < 1.0:
            confidence += 0.1

        return [PrecursorDetection(
            tipo=PrecursorType.SILENT_TRIGGER,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.SILENT_TRIGGER],
            station="global",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "kp_median": float(np.median(kp_list)),
                "kp_max": float(max(kp_list)),
                "kp_mean": kp_mean,
                "calm_duration_h": len(kp_list) * 3,
            },
        )]

    def _scan_seismic_cluster(
        self, seismic_mags: Optional[Any]
    ) -> List[PrecursorDetection]:
        if seismic_mags is None:
            return []

        m4_count = int(np.sum(seismic_mags >= 4.0))
        if not detect_seismic_cluster(m4_count):
            return []

        confidence = 0.7
        if m4_count >= 20:
            confidence += 0.15
        max_mag = float(np.max(seismic_mags))
        if max_mag >= 5.5:
            confidence += 0.1

        return [PrecursorDetection(
            tipo=PrecursorType.SEISMIC_CLUSTER,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.SEISMIC_CLUSTER],
            station="regional",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "event_count": m4_count,
                "max_magnitude": max_mag,
                "total_events": len(seismic_mags),
            },
        )]

    def _scan_volcanic(
        self,
        air_quality: Dict[str, Any],
        seismic_mags: Optional[Any],
        atmospheric: List[Dict[str, Any]],
    ) -> List[PrecursorDetection]:
        so2 = air_quality.get("so2", 0.0)
        seismic_count = 0
        if seismic_mags is not None:
            seismic_count = int(np.sum(seismic_mags >= 3.0))

        if not detect_volcanic_precursor(so2, seismic_count):
            return []

        confidence = 0.6
        if so2 > 200:
            confidence += 0.15
        if seismic_count >= 10:
            confidence += 0.1

        lat, lon = None, None
        station = "regional"
        if atmospheric:
            station = atmospheric[0].get("station", "regional")
            lat = atmospheric[0].get("lat")
            lon = atmospheric[0].get("lon")

        return [PrecursorDetection(
            tipo=PrecursorType.VOLCANICO,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.VOLCANICO],
            station=station,
            lat=lat,
            lon=lon,
            confidence=min(confidence, 0.95),
            values={
                "so2_mass": so2,
                "seismic_count": seismic_count,
            },
        )]

    def _scan_schumann(
        self, schumann_hz: Optional[float], schumann_pct: float
    ) -> List[PrecursorDetection]:
        if schumann_hz is None:
            return []

        deviation = abs(schumann_hz - 7.83)
        if deviation < 0.5 and schumann_pct < 150:
            return []

        confidence = 0.5
        if deviation >= 1.0:
            confidence += 0.2
        if schumann_pct >= 200:
            confidence += 0.15

        return [PrecursorDetection(
            tipo=PrecursorType.SCHUMANN,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.SCHUMANN],
            station="global",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "schumann_hz": schumann_hz,
                "deviation_hz": deviation,
                "schumann_activity_pct": schumann_pct,
            },
        )]

    def _scan_tormenta_solar(
        self, bz: float, kp: float, viento: float
    ) -> List[PrecursorDetection]:
        if bz > -10.0 or kp < 5.0:
            return []

        confidence = 0.7
        if bz < -20.0:
            confidence += 0.15
        if viento > 600:
            confidence += 0.1

        return [PrecursorDetection(
            tipo=PrecursorType.TORMENTA_SOLAR,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.TORMENTA_SOLAR],
            station="global",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "bz_nT": bz,
                "kp": kp,
                "viento_kms": viento,
            },
        )]

    def _scan_perturbacion_geomagnetica(
        self, bz: float, kp: float
    ) -> List[PrecursorDetection]:
        if bz > -5.0 or kp < 3.0:
            return []
        if bz <= -10.0 and kp >= 5.0:
            return []

        confidence = 0.55
        if abs(bz) > 7:
            confidence += 0.1
        if kp >= 4:
            confidence += 0.1

        return [PrecursorDetection(
            tipo=PrecursorType.PERTURBACION_GEOMAGNETICA,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.PERTURBACION_GEOMAGNETICA],
            station="global",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "bz_nT": bz,
                "kp": kp,
            },
        )]

    def _scan_sprites_rojos(
        self, atmospheric: List[Dict[str, Any]]
    ) -> List[PrecursorDetection]:
        results = []
        for reading in atmospheric:
            weather_id = reading.get("weather_id", 800)
            temp_c = reading.get("temp_c", 20.0)
            pressure = reading.get("pressure_hpa", 1013.0)
            clouds = reading.get("clouds_pct", 0)

            if detect_sprite_rojo(weather_id, temp_c, pressure, clouds):
                confidence = 0.65
                if pressure < 1000:
                    confidence += 0.15
                if temp_c > 32:
                    confidence += 0.1

                results.append(PrecursorDetection(
                    tipo=PrecursorType.SPRITE_ROJO,
                    display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.SPRITE_ROJO],
                    station=reading.get("station", "unknown"),
                    lat=reading.get("lat"),
                    lon=reading.get("lon"),
                    confidence=min(confidence, 0.95),
                    values={
                        "weather_id": weather_id,
                        "temp_c": temp_c,
                        "pressure_hpa": pressure,
                        "clouds_pct": clouds,
                    },
                ))
        return results

    def _scan_hurricanes(
        self, hurricane_data: Dict[str, Any]
    ) -> List[PrecursorDetection]:
        cyclones = hurricane_data.get("active_cyclones", [])
        results = []
        for cyc in cyclones:
            category = cyc.get("category", 0)
            distance = cyc.get("distance_deg", 999)

            if not detect_hurricane_proximity(category, distance):
                continue

            confidence = 0.6
            if category >= 3:
                confidence += 0.2
            elif category >= 2:
                confidence += 0.1
            if distance < 5:
                confidence += 0.1

            results.append(PrecursorDetection(
                tipo=PrecursorType.HURACAN,
                display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.HURACAN],
                station=cyc.get("name", "unknown"),
                lat=cyc.get("lat"),
                lon=cyc.get("lon"),
                confidence=min(confidence, 0.95),
                values={
                    "category": category,
                    "max_wind_kt": cyc.get("max_wind_kt", 0),
                    "pressure_mb": cyc.get("pressure_mb", 1013),
                    "distance_deg": distance,
                },
            ))
        return results

    def _scan_tsunami(
        self, seismic_mags: Optional[Any], delta_data: Dict[str, Any]
    ) -> List[PrecursorDetection]:
        if seismic_mags is None:
            return []

        max_mag = float(np.max(seismic_mags)) if len(seismic_mags) > 0 else 0.0
        depth_km = delta_data.get("max_quake_depth_km", 30.0)

        if not detect_tsunami_potential(max_mag, depth_km):
            return []

        confidence = 0.7
        if max_mag >= 8.0:
            confidence += 0.15
        if depth_km < 30:
            confidence += 0.1

        return [PrecursorDetection(
            tipo=PrecursorType.TSUNAMI,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.TSUNAMI],
            station="regional",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "magnitude": max_mag,
                "depth_km": depth_km,
            },
        )]

    def _scan_financial_correlation(
        self, financial_data: Dict[str, Any]
    ) -> List[PrecursorDetection]:
        fear_greed = financial_data.get("fear_greed", 50)
        vix = financial_data.get("vix", 20.0)
        btc_change = financial_data.get("btc_change_pct", 0.0)
        market_signal = financial_data.get("market_signal", "neutral")

        extreme_fear = fear_greed < 20
        vix_spike = vix > 30
        btc_crash = btc_change < -10.0
        bearish = market_signal in ("bearish", "alert")

        active_signals = sum([extreme_fear, vix_spike, btc_crash, bearish])
        if active_signals < 2:
            return []

        confidence = 0.5 + (active_signals * 0.1)

        return [PrecursorDetection(
            tipo=PrecursorType.CORRELACION_FINANCIERA,
            display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.CORRELACION_FINANCIERA],
            station="global",
            lat=None,
            lon=None,
            confidence=min(confidence, 0.95),
            values={
                "fear_greed": fear_greed,
                "vix": vix,
                "btc_change_pct": btc_change,
                "market_signal": market_signal,
                "active_financial_signals": active_signals,
            },
        )]

    def _scan_precipitacion(
        self,
        atmospheric: List[Dict[str, Any]],
        schumann_hz: Optional[float],
    ) -> List[PrecursorDetection]:
        """
        Detect anomalous precipitation potential via the Schumann-modular formula:

            Π_i(t) = μ_i(t) · ( Φ_i(t)  mod  Φ_S(t) )

        where μ_i is local humidity, Φ_i is the regional atmospheric energy
        flux proxy, and Φ_S is the Schumann modal reference scale.
        A high Π_i means large residual energy (not absorbed by the global
        resonator) is available to couple with moisture and reorganise as
        precipitation.
        """
        if schumann_hz is None or schumann_hz <= 0:
            return []

        results = []
        for reading in atmospheric:
            humidity = reading.get("humidity_pct", 50.0)
            temp_c = reading.get("temp_c", 20.0)
            clouds = reading.get("clouds_pct", 0.0)

            if not detect_precipitacion_potencial(humidity, temp_c, clouds, schumann_hz):
                continue

            pi_i = compute_precipitacion_potencial(humidity, temp_c, clouds, schumann_hz)

            confidence = _PREC_CONF_BASE
            if humidity >= _PREC_HUMIDITY_HIGH:
                confidence += _PREC_CONF_HUMIDITY_BOOST
            if clouds >= _PREC_CLOUDS_HIGH:
                confidence += _PREC_CONF_CLOUDS_BOOST
            if pi_i >= _PREC_PI_VERY_HIGH:
                confidence += _PREC_CONF_PI_BOOST

            results.append(PrecursorDetection(
                tipo=PrecursorType.PRECIPITACION,
                display_name=PRECURSOR_DISPLAY_NAMES[PrecursorType.PRECIPITACION],
                station=reading.get("station", "unknown"),
                lat=reading.get("lat"),
                lon=reading.get("lon"),
                confidence=min(confidence, 0.95),
                values={
                    "humidity_pct": humidity,
                    "temp_c": temp_c,
                    "clouds_pct": clouds,
                    "schumann_hz": schumann_hz,
                    "pi_i": round(pi_i, 3),
                },
            ))
        return results
