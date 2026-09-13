"""
Precursor Type Registry — All Natural Event Precursor Categories

Extracted from legacy TITAN V32/V46/V53 and Sentinel Orchestrator Jobs v2.0.
Each type maps to specific detection logic and validation windows.

The system detects precursors for:
  - Earthquakes (via Bz, Kp, Schumann, pressure, SO2, silent triggers, swarms)
  - Solar/geomagnetic storms (via NOAA real-time space weather)
  - Ionospheric anomalies (Blue Jets, TEC proxy)
  - Atmospheric anomalies (fog, pressure drops, chemical outgassing)
  - Volcanic precursors (SO2 spikes + seismic coupling)
  - Astrophysical events (GRBs)
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class PrecursorType(Enum):
    SCHUMANN = "SCHUMANN"
    SILENT_TRIGGER = "SILENT_TRIGGER"
    SEISMIC_CLUSTER = "SEISMIC_CLUSTER"
    BLUE_JET = "BLUE_JET"
    SPRITE_ROJO = "SPRITE_ROJO"
    NIEBLA_TULE = "NIEBLA_TULE"
    TORMENTA_SOLAR = "TORMENTA_SOLAR"
    PERTURBACION_GEOMAGNETICA = "PERTURBACION_GEOMAGNETICA"
    HURACAN = "HURACAN"
    TSUNAMI = "TSUNAMI"
    ML_INFERENCE = "ML_INFERENCE"
    GRB = "GRB"
    VOLCANICO = "VOLCANICO"
    FANTASMA = "FANTASMA"
    CORRELACION_FINANCIERA = "CORRELACION_FINANCIERA"
    PRECIPITACION = "PRECIPITACION"


@dataclass
class PrecursorProfile:
    tipo: PrecursorType
    description: str
    validation_window_hours: float
    min_magnitude_usgs: float
    radius_degrees: float
    variables: tuple


PRECURSOR_PROFILES = {
    PrecursorType.SCHUMANN: PrecursorProfile(
        tipo=PrecursorType.SCHUMANN,
        description="Resonancia Schumann excitation — deviation from 7.83 Hz baseline",
        validation_window_hours=72.0,
        min_magnitude_usgs=4.5,
        radius_degrees=10.0,
        variables=("schumann_hz", "schumann_activity_pct"),
    ),
    PrecursorType.SILENT_TRIGGER: PrecursorProfile(
        tipo=PrecursorType.SILENT_TRIGGER,
        description="Extreme magnetic calm — all Kp < 2.0 for 24h sustained",
        validation_window_hours=48.0,
        min_magnitude_usgs=5.0,
        radius_degrees=5.0,
        variables=("kp_median", "kp_max", "calm_duration_h"),
    ),
    PrecursorType.SEISMIC_CLUSTER: PrecursorProfile(
        tipo=PrecursorType.SEISMIC_CLUSTER,
        description="Seismic swarm — 10+ M4.0+ events within 24h in a region",
        validation_window_hours=48.0,
        min_magnitude_usgs=5.0,
        radius_degrees=5.0,
        variables=("event_count", "max_magnitude", "cluster_centroid"),
    ),
    PrecursorType.BLUE_JET: PrecursorProfile(
        tipo=PrecursorType.BLUE_JET,
        description="Ionospheric discharge — thunderstorm + temp > 25°C (pressure coupling)",
        validation_window_hours=72.0,
        min_magnitude_usgs=4.5,
        radius_degrees=8.0,
        variables=("temp_c", "pressure_hpa", "weather_id", "so2"),
    ),
    PrecursorType.SPRITE_ROJO: PrecursorProfile(
        tipo=PrecursorType.SPRITE_ROJO,
        description="Red Sprite — mesospheric discharge above intense thunderstorm (lightning rate > 100/hr)",
        validation_window_hours=72.0,
        min_magnitude_usgs=4.5,
        radius_degrees=10.0,
        variables=("weather_id", "temp_c", "pressure_hpa", "clouds_pct"),
    ),
    PrecursorType.NIEBLA_TULE: PrecursorProfile(
        tipo=PrecursorType.NIEBLA_TULE,
        description="Dense fog anomaly — humidity > 90%%, visibility < 1000m",
        validation_window_hours=72.0,
        min_magnitude_usgs=4.5,
        radius_degrees=5.0,
        variables=("humidity_pct", "visibility_m"),
    ),
    PrecursorType.TORMENTA_SOLAR: PrecursorProfile(
        tipo=PrecursorType.TORMENTA_SOLAR,
        description="Solar/geomagnetic storm — Bz severely southward + Kp >= 5",
        validation_window_hours=96.0,
        min_magnitude_usgs=4.5,
        radius_degrees=15.0,
        variables=("bz_nT", "kp", "viento_kms", "proton_flux"),
    ),
    PrecursorType.PERTURBACION_GEOMAGNETICA: PrecursorProfile(
        tipo=PrecursorType.PERTURBACION_GEOMAGNETICA,
        description="Geomagnetic perturbation — moderate Bz + elevated Kp",
        validation_window_hours=96.0,
        min_magnitude_usgs=4.5,
        radius_degrees=10.0,
        variables=("bz_nT", "kp", "dst_index"),
    ),
    PrecursorType.HURACAN: PrecursorProfile(
        tipo=PrecursorType.HURACAN,
        description="Tropical cyclone proximity — NHC active storm within monitoring radius",
        validation_window_hours=120.0,
        min_magnitude_usgs=0.0,
        radius_degrees=15.0,
        variables=("category", "max_wind_kt", "pressure_mb", "distance_deg"),
    ),
    PrecursorType.TSUNAMI: PrecursorProfile(
        tipo=PrecursorType.TSUNAMI,
        description="Tsunamigenic potential — M7.0+ shallow undersea earthquake",
        validation_window_hours=24.0,
        min_magnitude_usgs=7.0,
        radius_degrees=20.0,
        variables=("magnitude", "depth_km", "coast_distance"),
    ),
    PrecursorType.ML_INFERENCE: PrecursorProfile(
        tipo=PrecursorType.ML_INFERENCE,
        description="Machine learning composite inference from all features",
        validation_window_hours=48.0,
        min_magnitude_usgs=5.0,
        radius_degrees=5.0,
        variables=("ml_score", "feature_vector"),
    ),
    PrecursorType.GRB: PrecursorProfile(
        tipo=PrecursorType.GRB,
        description="Gamma-ray burst detection — astrophysical monitoring",
        validation_window_hours=168.0,
        min_magnitude_usgs=0.0,
        radius_degrees=180.0,
        variables=("grb_fluence", "grb_duration"),
    ),
    PrecursorType.VOLCANICO: PrecursorProfile(
        tipo=PrecursorType.VOLCANICO,
        description="Volcanic precursors — SO2 outgassing + seismic swarm coupling",
        validation_window_hours=72.0,
        min_magnitude_usgs=4.0,
        radius_degrees=3.0,
        variables=("so2_mass", "seismic_count", "pressure_hpa"),
    ),
    PrecursorType.FANTASMA: PrecursorProfile(
        tipo=PrecursorType.FANTASMA,
        description="TITAN V32 fantasma composite — core risk formula",
        validation_window_hours=72.0,
        min_magnitude_usgs=4.5,
        radius_degrees=5.0,
        variables=("bz_nT", "viento_kms", "schumann_wpc", "pressure_hpa", "kp", "lod_ms"),
    ),
    PrecursorType.CORRELACION_FINANCIERA: PrecursorProfile(
        tipo=PrecursorType.CORRELACION_FINANCIERA,
        description="Financial correlation — crypto/bolsa anomaly coinciding with geophysical precursors",
        validation_window_hours=72.0,
        min_magnitude_usgs=0.0,
        radius_degrees=180.0,
        variables=("fear_greed", "vix", "btc_change_pct", "market_signal"),
    ),
    PrecursorType.PRECIPITACION: PrecursorProfile(
        tipo=PrecursorType.PRECIPITACION,
        description=(
            "Precipitation potential — Schumann-modular coupling: "
            "Π_i(t) = μ_i(t)·(Φ_i(t) mod Φ_S(t)); "
            "residual atmospheric energy not absorbed by Schumann modes, "
            "weighted by local condensation availability"
        ),
        validation_window_hours=48.0,
        min_magnitude_usgs=0.0,
        radius_degrees=5.0,
        variables=("humidity_pct", "temp_c", "clouds_pct", "schumann_hz", "pi_i"),
    ),
}


PRECURSOR_DISPLAY_NAMES = {
    PrecursorType.SCHUMANN: "Resonancia Schumann",
    PrecursorType.SILENT_TRIGGER: "Patrón Silent Trigger (Calma)",
    PrecursorType.SEISMIC_CLUSTER: "Enjambre Sísmico Local",
    PrecursorType.BLUE_JET: "Blue Jet (Fuga Ionosférica)",
    PrecursorType.SPRITE_ROJO: "Sprite Rojo (Descarga Mesosférica)",
    PrecursorType.NIEBLA_TULE: "Niebla Tule (Anomalía)",
    PrecursorType.TORMENTA_SOLAR: "Tormenta Solar",
    PrecursorType.PERTURBACION_GEOMAGNETICA: "Perturbación Geomagnética",
    PrecursorType.HURACAN: "Huracán / Ciclón Tropical",
    PrecursorType.TSUNAMI: "Tsunami / Maremoto",
    PrecursorType.ML_INFERENCE: "Inferencia ML",
    PrecursorType.GRB: "Gamma-Ray Burst",
    PrecursorType.VOLCANICO: "Precursor Volcánico",
    PrecursorType.FANTASMA: "Índice Fantasma (V32)",
    PrecursorType.CORRELACION_FINANCIERA: "Correlación Financiera",
    PrecursorType.PRECIPITACION: "Precipitación Potencial (Schumann-Modular)",
}


def get_profile(tipo: PrecursorType) -> PrecursorProfile:
    return PRECURSOR_PROFILES[tipo]


def detect_blue_jet(temp_c: float, weather_id: int, pressure_hpa: float = 1013.0) -> bool:
    is_thunderstorm = 200 <= weather_id <= 232
    return is_thunderstorm and temp_c > 25.0


def detect_niebla_tule(humidity_pct: float, visibility_m: float) -> bool:
    return humidity_pct > 90.0 and visibility_m < 1000.0


def detect_silent_trigger(kp_series: list, min_hours: float = 12.0) -> bool:
    if len(kp_series) < 12:
        return False
    return all(kp < 2.0 for kp in kp_series) and (sum(kp_series) / len(kp_series)) <= 1.5


def detect_seismic_cluster(event_count_24h: int, threshold: int = 10) -> bool:
    return event_count_24h >= threshold


def detect_volcanic_precursor(so2_mass: float, seismic_count: int) -> bool:
    return so2_mass > 100.0 and seismic_count >= 3


def detect_sprite_rojo(
    weather_id: int, temp_c: float, pressure_hpa: float, clouds_pct: float = 100.0
) -> bool:
    """Red Sprites occur above intense thunderstorms with low pressure and full cloud cover."""
    is_severe_storm = 200 <= weather_id <= 232
    return is_severe_storm and temp_c > 28.0 and pressure_hpa < 1005.0 and clouds_pct >= 80


def detect_hurricane_proximity(
    category: int, distance_deg: float, max_distance: float = 10.0
) -> bool:
    return category >= 1 and distance_deg <= max_distance


def detect_tsunami_potential(
    magnitude: float, depth_km: float
) -> bool:
    return magnitude >= 7.0 and depth_km < 70.0


# ── Precipitation potential — Schumann-modular formula ───────────────────────
#
# Variant 3 (node theory):
#   Π_i(t) = μ_i(t) · ( Φ_i(t)  mod  Φ_S(t) )
#
#   μ_i(t)  — condensation availability  = humidity_pct / 100
#   Φ_i(t)  — regional atmospheric energy flux proxy (K-scale)
#             = temp_c × (clouds_pct / 100) + 273.15
#             (temperature weighted by cloud loading; Kelvin baseline keeps
#              the value above zero and in the same order of magnitude as Φ_S)
#   Φ_S(t)  — Schumann modal reference scale (K-scale)
#             = schumann_hz × 10.0
#             (converts Hz to K-equivalent; standard 7.83 Hz → 78.3 K-scale)
#
# Physical interpretation: the residual (Φ_i mod Φ_S) represents atmospheric
# energy that does NOT project cleanly onto the Schumann resonant mode.  When
# this "structured surplus" couples with sufficient moisture (μ_i), the system
# reorganises as precipitation.  A large residual + high humidity → Π_i high.

_PRECIPITACION_THRESHOLD: float = 30.0


def compute_precipitacion_potencial(
    humidity_pct: float,
    temp_c: float,
    clouds_pct: float,
    schumann_hz: float,
) -> float:
    """
    Compute regional precipitation potential Π_i(t).

    Returns a dimensionless value (K-scale) — values ≥ 30 indicate an
    anomalous coupling between residual atmospheric energy and Schumann modes.
    """
    mu_i = humidity_pct / 100.0
    phi_i = temp_c * (clouds_pct / 100.0) + 273.15
    phi_s = schumann_hz * 10.0

    if phi_s < 1e-6:
        return 0.0

    residual = phi_i % phi_s
    return float(mu_i * residual)


def detect_precipitacion_potencial(
    humidity_pct: float,
    temp_c: float,
    clouds_pct: float,
    schumann_hz: float,
    threshold: float = _PRECIPITACION_THRESHOLD,
) -> bool:
    """Return True when the Schumann-modular precipitation potential exceeds threshold."""
    return compute_precipitacion_potencial(
        humidity_pct, temp_c, clouds_pct, schumann_hz
    ) >= threshold
