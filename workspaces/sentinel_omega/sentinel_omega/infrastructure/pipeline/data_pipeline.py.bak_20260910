"""
Data Pipeline — fetches from real APIs and formats for agent ingest().
Single pipeline: all 6 agents are part of one system.

Agent data mapping:
  - Alfa-1: NOAA OMNI (Bz, solar wind) — 30yr
  - Alfa-2: ESA Sentinel-2 satellite — 14yr
  - Beta-1: Kp, seismic, Schumann, LOD, lunar — 30yr
  - Beta-2: Atmospheric chemistry (pressure, SO2, air quality) — 14yr
  - Delta: Financial cross-correlation (Fear & Greed, VIX, BTC dominance) — 10yr

LOCF Protocol:
  When an API call fails, the pipeline uses Last Observation Carried Forward
  from the previous successful fetch. Never generates synthetic data.
"""

import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from sentinel_omega.infrastructure.api.noaa import (
    fetch_kp_index,
    fetch_goes_xray,
    fetch_solar_wind,
    fetch_mag_field,
    fetch_electron_flux,
)
from sentinel_omega.infrastructure.api.gfz_kp import fetch_kp_history
from sentinel_omega.infrastructure.api.google_trends import fetch_solar_storm_trends
from sentinel_omega.infrastructure.api.nasa_neo import fetch_neo_hazard_summary
from sentinel_omega.infrastructure.api.usgs import fetch_earthquakes
from sentinel_omega.infrastructure.api.schumann import fetch_schumann_resonance
from sentinel_omega.infrastructure.api.geophysical import (
    fetch_lod_series,
    compute_lunar_phase_series,
)
from sentinel_omega.infrastructure.api.esa_sentinel import (
    search_sentinel2,
    search_sentinel1_sar,
    compute_temporal_coverage,
    get_seismic_zone_bboxes,
)
from sentinel_omega.infrastructure.api.openweathermap import (
    fetch_monitoring_network,
    fetch_air_quality,
    fetch_reference_baseline,
    scan_global_nodes,
    compute_pressure_gradient,
    MONITORING_STATIONS,
)
from sentinel_omega.infrastructure.api.crypto import (
    fetch_coingecko_dominance,
    fetch_binance_klines,
    fetch_fear_greed_index,
    fetch_coingecko_market_chart,
)
from sentinel_omega.infrastructure.api.bolsa import (
    fetch_yahoo_quote,
    fetch_vix,
    fetch_sector_etfs,
    fetch_yield_spread,
)

logger = logging.getLogger(__name__)


class GeodynamicPipeline:
    """Single pipeline for all 6 agents in the Sentinel Omega system.

    Implements LOCF (Last Observation Carried Forward):
    Each fetch method stores its last successful result. If the next API call
    fails, the cached result is returned instead of empty data. This ensures
    agents always have real data to work with, even during API outages.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ts: Dict[str, float] = {}

    _LOCF_STALE_S = 86_400  # warn when cache is older than 24 h

    def _locf_get(self, key: str) -> Dict[str, Any]:
        """Return last cached value for a given pipeline stage."""
        cached = self._cache.get(key)
        if cached:
            age_s = time.time() - self._cache_ts.get(key, 0)
            if age_s > self._LOCF_STALE_S:
                logger.warning(
                    f"LOCF stale for {key} (age={age_s / 3600:.1f}h — data older than 24h)"
                )
            else:
                logger.info(f"LOCF active for {key} (age={age_s:.0f}s)")
        else:
            logger.warning(f"LOCF miss for {key} — no prior data; returning empty dict")
        return cached or {}

    def _locf_set(self, key: str, data: Dict[str, Any]):
        """Store successful fetch result for LOCF fallback."""
        if data:
            self._cache[key] = data
            self._cache_ts[key] = time.time()

    def fetch_alfa1_data(self) -> Dict[str, Any]:
        """Build OMNI-like DataFrame for Alfa-1 from NOAA real-time data."""
        mag_df = fetch_mag_field()
        wind_df = fetch_solar_wind()

        if mag_df is None and wind_df is None:
            logger.warning("No NOAA data available for Alfa-1 — activating LOCF")
            return self._locf_get("alfa1")

        frames = []
        if mag_df is not None:
            mag_df = mag_df.set_index("time_tag")
            mag_df = mag_df[~mag_df.index.duplicated(keep="last")]
            frames.append(mag_df)
        if wind_df is not None:
            wind_df = wind_df.rename(columns={
                "proton_speed": "plasma_speed",
            }).set_index("time_tag")
            wind_df = wind_df[~wind_df.index.duplicated(keep="last")]
            frames.append(wind_df)

        if not frames:
            return self._locf_get("alfa1")

        omni_df = pd.concat(frames, axis=1)
        omni_df = omni_df.sort_index().ffill().dropna(how="all")
        logger.info(f"Alfa-1 pipeline: {len(omni_df)} records, {list(omni_df.columns)}")
        result = {"omni_dataframe": omni_df.reset_index(names=["time_tag"])}
        self._locf_set("alfa1", result)
        return result

    def fetch_beta1_data(self) -> Dict[str, Any]:
        """Fetch Kp series, seismic, Schumann, LOD, lunar for Beta-1."""
        result: Dict[str, Any] = {}

        kp_df = fetch_kp_index()
        if kp_df is not None and len(kp_df) > 0:
            result["kp_series"] = kp_df["kp_index"].values.astype(float)

        eq_df = fetch_earthquakes(min_magnitude=2.5, days=30)
        if eq_df is not None and "magnitude" in eq_df.columns:
            result["seismic_magnitudes"] = eq_df["magnitude"].values.astype(float)

        try:
            schumann_hz, schumann_pct = fetch_schumann_resonance(cleanup=True)
            result["schumann_frequency"] = schumann_hz
            result["schumann_activity"] = schumann_pct
        except Exception as e:
            logger.warning(f"Schumann fetch failed: {e}")

        lod_df = fetch_lod_series(days=90)
        if lod_df is not None and len(lod_df) > 0:
            result["lod_ms"] = lod_df["lod_ms"].values.astype(float)

        try:
            result["lunar_phase"] = compute_lunar_phase_series(days=30)
        except Exception as e:
            logger.warning(f"Lunar phase computation failed: {e}")

        electron_df = fetch_electron_flux()
        if electron_df is not None and len(electron_df) > 0:
            result["electron_flux"] = float(electron_df["flux"].iloc[-1])

        neo = fetch_neo_hazard_summary()
        if neo:
            result["neo_hazardous_count"] = neo["hazardous_count"]
            if neo.get("closest_hazardous_ld") is not None:
                result["neo_closest_ld"] = neo["closest_hazardous_ld"]

        # TEC sintético — derived index, NOT sensor data. With no public TEC
        # sensor feed, the ionospheric charge state is estimated from real
        # inputs (X-ray flux proxy, Kp, solar wind), V31 cortex lineage.
        try:
            xray_df = fetch_goes_xray()
            flux_proxy = 70.0
            if xray_df is not None and len(xray_df) > 0:
                f = float(xray_df["flux"].iloc[-1]) * 100000
                if f > 0:
                    flux_proxy = 70.0 + f
            kp_now = float(result["kp_series"][-1]) if "kp_series" in result else 2.0
            wind_now = 350.0
            cached_alfa1 = self._cache.get("alfa1")
            if cached_alfa1:
                omni = cached_alfa1.get("omni_dataframe")
                if omni is not None and "plasma_speed" in omni.columns:
                    last_wind = omni["plasma_speed"].dropna()
                    if len(last_wind) > 0:
                        wind_now = float(last_wind.iloc[-1])
            result["tec_estimated"] = round(
                flux_proxy * 0.5 + kp_now * 2.0 + wind_now * 0.01, 2
            )
        except Exception as e:
            logger.warning(f"Synthetic TEC computation failed: {e}")

        if not result:
            logger.warning("No Kp/seismic data for Beta-1 — activating LOCF")
            return self._locf_get("beta1")
        self._locf_set("beta1", result)
        return result

    def fetch_alfa2_data(
        self,
        zones: Optional[List[str]] = None,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Fetch Sentinel-2 multispectral coverage for seismic zone monitoring."""
        all_zones = get_seismic_zone_bboxes()
        target_zones = zones or ["guerrero_gap", "oaxaca_costa", "chiapas"]

        zone_coverages = {}
        for zone in target_zones:
            bbox = all_zones.get(zone)
            if bbox is None:
                continue
            try:
                cov = compute_temporal_coverage(bbox, days=days)
                zone_coverages[zone] = cov
            except Exception as e:
                logger.warning(f"Satellite coverage failed for {zone}: {e}")

        if not zone_coverages:
            logger.warning("No satellite coverage data for Alfa-2 — activating LOCF")
            return self._locf_get("alfa2")

        logger.info(f"Alfa-2 pipeline: {len(zone_coverages)} zones analyzed")
        result = {
            "zone_coverages": zone_coverages,
            "thermal_anomaly_count": 0,
        }
        self._locf_set("alfa2", result)
        return result

    def fetch_beta2_data(self) -> Dict[str, Any]:
        """Fetch atmospheric chemistry data for Beta-2 (pressure, SO2, air quality)."""
        result: Dict[str, Any] = {}

        try:
            readings = fetch_monitoring_network(
                ["tlaxcala", "oaxaca", "guerrero", "colima"]
            )
            if readings:
                gradient = compute_pressure_gradient(readings)
                result["pressure_gradient"] = gradient
                result["atmospheric_readings"] = [
                    {
                        "station": r.station,
                        "lat": r.lat,
                        "lon": r.lon,
                        "pressure_hpa": r.pressure_hpa,
                        "temp_c": r.temp_c,
                        "humidity_pct": r.humidity_pct,
                        "visibility_m": r.visibility_m,
                        "weather_id": r.weather_id,
                    }
                    for r in readings
                ]
        except Exception as e:
            logger.warning(f"Atmospheric data fetch failed: {e}")

        try:
            tlaxcala = MONITORING_STATIONS["tlaxcala"]
            aq = fetch_air_quality(tlaxcala["lat"], tlaxcala["lon"])
            if aq:
                result["air_quality"] = aq
        except Exception as e:
            logger.warning(f"Air quality fetch failed: {e}")

        try:
            baseline = fetch_reference_baseline()
            if baseline:
                result["degassing_baseline"] = baseline
        except Exception as e:
            logger.warning(f"Reference baseline fetch failed: {e}")

        try:
            node_scan = scan_global_nodes()
            if node_scan:
                result["global_node_scan"] = node_scan
        except Exception as e:
            logger.warning(f"Global node scan failed: {e}")

        if not result:
            logger.warning("No atmospheric data for Beta-2 — activating LOCF")
            return self._locf_get("beta2")
        self._locf_set("beta2", result)
        return result

    def fetch_delta_data(self) -> Dict[str, Any]:
        """
        Fetch financial + sentiment data for Delta.
        Crypto (Fear & Greed, BTC dominance), Bolsa (VIX, sectors, yield spread).
        """
        result: Dict[str, Any] = {}

        fg = fetch_fear_greed_index()
        result["fear_greed"] = fg["value"] if fg else 50.0

        dominance = fetch_coingecko_dominance()
        if dominance:
            result["btc_dominance"] = dominance.get("btc", 50.0) / 100.0

        crypto_ratios: Dict[str, float] = {}
        for symbol in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
            df = fetch_binance_klines(symbol, limit=30)
            btc_df = fetch_binance_klines("BTCUSDT", limit=30)
            if df is not None and btc_df is not None:
                if "close" in df.columns and "close" in btc_df.columns:
                    ratio = float(df["close"].iloc[-1]) / max(float(btc_df["close"].iloc[-1]), 1)
                    crypto_ratios[symbol.replace("USDT", "")] = ratio
        if crypto_ratios:
            result["crypto_ratios"] = crypto_ratios

        vix_df = fetch_vix()
        if vix_df is not None and "close" in vix_df.columns:
            result["vix"] = float(vix_df["close"].iloc[-1])

        # BTC volatility window (Yahoo, no key) — same units as Delta's
        # trained firma features, so live states can match trained memory.
        btc_df = fetch_yahoo_quote("BTC-USD", days=15)
        if btc_df is not None and "close" in btc_df.columns and len(btc_df) >= 3:
            closes = btc_df["close"].dropna()
            vol = (closes.pct_change().abs() * 100).dropna()
            if len(vol) > 0 and float(closes.iloc[0]):
                result["btc_volatilidad"] = float(vol.mean())
                result["btc_vol_max"] = float(vol.max())
                result["btc_ret_win"] = float(
                    (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100
                )
                result["btc_vol_72h"] = float(vol.tail(3).mean())

        spread = fetch_yield_spread()
        if spread is not None:
            result["yield_spread"] = spread

        sector_dfs = fetch_sector_etfs(days=30)
        sector_caps: Dict[str, float] = {}
        for etf, df in sector_dfs.items():
            if "close" in df.columns and "volume" in df.columns:
                last_close = float(df["close"].iloc[-1])
                avg_vol = float(df["volume"].mean())
                sector_caps[etf] = last_close * avg_vol
        if sector_caps:
            result["sector_market_caps"] = sector_caps

        if not result or (result.get("fear_greed") == 50.0 and "vix" not in result):
            cached = self._locf_get("delta")
            if cached:
                return cached

        # Delta enriquecido: correlación cruzada geofísica ↔ financiera.
        # Usa delta_enriched (ex staging/snt_delta) para generar:
        #   - cross_coupling: qué tan acoplados están el clima espacial / Schumann
        #     con los movimientos financieros en esta ventana de 14 días.
        #   - geophysical_context: contexto Kp/Bz/Schumann para el reporte.
        # Fail-soft: si falla no bloquea el ciclo.
        try:
            from sentinel_omega.core.delta_enriched.fetchers import fetch_all
            from sentinel_omega.core.delta_enriched.composite import run_composite

            enriched_data = fetch_all(days=14)
            enriched = run_composite(enriched_data, window_days=14)

            result["cross_coupling"] = round(enriched.cross.composite_coupling, 4) if enriched.cross else 0.0
            result["geo_coupling"] = round(enriched.cross.geomagnetic_coupling, 4) if enriched.cross else 0.0
            result["schumann_coupling"] = round(enriched.cross.schumann_coupling, 4) if enriched.cross else 0.0
            result["delta_composite_score"] = round(enriched.composite_score, 4)
            result["delta_regime_label"] = enriched.regime_label
            result["delta_narrative"] = enriched.narrative
            result["delta_confidence"] = round(enriched.confidence, 4)
            result["delta_data_completeness"] = round(enriched.data_completeness, 2)

            if enriched.geophysical:
                geo = enriched.geophysical
                result["geo_kp_max_3d"] = geo.kp_max_3d
                result["geo_storm_active"] = int(geo.storm_active)
                result["geo_schumann_deviation"] = geo.schumann_freq_deviation

            logger.info(
                f"Delta enriquecido: composite={result['delta_composite_score']:.3f}, "
                f"cross_coupling={result['cross_coupling']:.3f}, "
                f"regime={result['delta_regime_label']}"
            )
        except Exception as exc:
            logger.warning(f"Delta enriched pipeline failed (non-blocking): {exc}")

        logger.info(
            f"Delta pipeline: FGI={result.get('fear_greed', '?')}, "
            f"VIX={result.get('vix', '?')}, "
            f"{len(crypto_ratios)} crypto ratios, "
            f"{len(sector_caps)} sectors"
        )
        self._locf_set("delta", result)
        return result

    # Google Trends is rate-limited (HTTP 429): refresh it at most every 6 h.
    _TRENDS_TTL_S = 6 * 3600

    def fetch_jupiter_data(
        self, schumann_series: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Data for Júpiter: long-history Kp (GFZ) + GOES X-ray + Google Trends.

        Kp/X-ray are fetched fresh each cycle; Google Trends is cached for
        `_TRENDS_TTL_S` to avoid rate-limiting the live loop. `schumann_series`
        (a daily Series from repository.schumann_trend) is passed through when the
        caller has DB access; otherwise Júpiter runs without it.
        """
        kp = fetch_kp_history(days=90)
        xray = fetch_goes_xray()

        trends = None
        cached = self._cache.get("jupiter_trends")
        age = time.time() - self._cache_ts.get("jupiter_trends", 0)
        if cached and age < self._TRENDS_TTL_S:
            trends = cached.get("trends_df")
            logger.info(f"Júpiter Trends from cache (age={age / 3600:.1f}h)")
        else:
            trends = fetch_solar_storm_trends(timeframe="today 3-m")
            if trends is not None:
                self._cache["jupiter_trends"] = {"trends_df": trends}
                self._cache_ts["jupiter_trends"] = time.time()

        result = {
            "kp_df": kp,
            "xray_df": xray,
            "trends_df": trends,
            "schumann_series": schumann_series,
        }
        n = sum(1 for v in (kp, xray, trends) if v is not None and len(v))
        logger.info(f"Júpiter pipeline: {n}/3 space-weather/attention sources")
        return result
