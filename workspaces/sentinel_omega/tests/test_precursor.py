"""Tests for the precursor detection module (TITAN V32/V46 lineage)."""

import time

import numpy as np
import pandas as pd
import pytest

from sentinel_omega.core.precursor.risk_calculator import (
    PrecursorRisk,
    compute_fantasma,
    classify_risk,
    compute_risk_from_signals,
    format_risk_report,
    RISK_THRESHOLDS,
)
from sentinel_omega.core.precursor.assertivity import (
    AssertivityTracker,
    AssertivityResult,
    Prediction,
)
from sentinel_omega.core.precursor.precursor_types import (
    PrecursorType,
    PrecursorProfile,
    PRECURSOR_PROFILES,
    PRECURSOR_DISPLAY_NAMES,
    get_profile,
    detect_blue_jet,
    detect_niebla_tule,
    detect_silent_trigger,
    detect_sprite_rojo,
    detect_hurricane_proximity,
    detect_tsunami_potential,
    detect_seismic_cluster,
    detect_volcanic_precursor,
    compute_precipitacion_potencial,
    detect_precipitacion_potencial,
)


# ── Risk Calculator (TITAN V32 fantasma) ────────────────────────────


class TestFantasmaFormula:

    def test_zero_inputs_produce_low_risk(self):
        risk = compute_fantasma(bz=0, viento=0, sch_wpc=0)
        assert risk.fantasma == 0.0
        assert risk.risk_level == "LOW"

    def test_core_formula_matches_titan_v32(self):
        """fantasma = (viento * 0.02) + (abs(bz) ** 2) + (sch_wpc * 1.5)"""
        bz = -5.0
        viento = 400.0
        sch_wpc = 0.2

        risk = compute_fantasma(bz=bz, viento=viento, sch_wpc=sch_wpc)
        expected = (400 * 0.02) + (5.0 ** 2) + (0.2 * 1.5)
        assert abs(risk.fantasma - expected) < 0.01

    def test_bz_squared_contribution(self):
        risk = compute_fantasma(bz=-10.0, viento=0, sch_wpc=0)
        assert risk.bz_contribution == 100.0
        assert risk.fantasma >= 100.0

    def test_negative_bz_same_as_positive(self):
        r1 = compute_fantasma(bz=-8.0, viento=0, sch_wpc=0)
        r2 = compute_fantasma(bz=8.0, viento=0, sch_wpc=0)
        assert r1.bz_contribution == r2.bz_contribution

    def test_wind_contribution(self):
        risk = compute_fantasma(bz=0, viento=600.0, sch_wpc=0)
        assert risk.wind_contribution == 12.0

    def test_schumann_contribution(self):
        risk = compute_fantasma(bz=0, viento=0, sch_wpc=0.8)
        assert abs(risk.schumann_contribution - 1.2) < 1e-10

    def test_severe_storm_conditions(self):
        """Bz=-20, viento=800, Schumann excited → CRITICAL."""
        risk = compute_fantasma(bz=-20.0, viento=800.0, sch_wpc=0.5)
        assert risk.risk_level == "CRITICAL"
        assert risk.fantasma > 30.0

    def test_moderate_conditions(self):
        risk = compute_fantasma(bz=-3.0, viento=350.0, sch_wpc=0.1)
        expected = (350 * 0.02) + (3.0 ** 2) + (0.1 * 1.5)
        assert abs(risk.fantasma - expected) < 0.01
        assert risk.risk_level == "HIGH"

    def test_is_elevated_property(self):
        low = compute_fantasma(bz=0, viento=0, sch_wpc=0)
        high = compute_fantasma(bz=-10, viento=500, sch_wpc=0.5)
        assert not low.is_elevated
        assert high.is_elevated


class TestPressureModifier:

    def test_normal_pressure_no_modifier(self):
        risk = compute_fantasma(bz=-2, viento=300, sch_wpc=0, pressure_hpa=1015.0)
        assert risk.pressure_modifier == 0.0

    def test_low_pressure_adds_risk(self):
        risk = compute_fantasma(bz=-2, viento=300, sch_wpc=0, pressure_hpa=1000.0)
        assert risk.pressure_modifier > 0.0
        expected_mod = (1008.0 - 1000.0) / 5.0
        assert abs(risk.pressure_modifier - expected_mod) < 0.01

    def test_very_low_pressure_capped(self):
        risk = compute_fantasma(bz=0, viento=0, sch_wpc=0, pressure_hpa=960.0)
        assert risk.pressure_modifier <= 3.0


class TestKpModifier:

    def test_low_kp_no_multiplier(self):
        risk = compute_fantasma(bz=-3, viento=300, sch_wpc=0, kp=2.0)
        assert risk.kp_modifier == 1.0

    def test_storm_kp_multiplies(self):
        r_base = compute_fantasma(bz=-3, viento=300, sch_wpc=0, kp=0.0)
        r_storm = compute_fantasma(bz=-3, viento=300, sch_wpc=0, kp=7.0)
        assert r_storm.fantasma > r_base.fantasma
        assert r_storm.kp_modifier > 1.0


class TestLodModifier:

    def test_normal_lod_no_modifier(self):
        risk = compute_fantasma(bz=0, viento=0, sch_wpc=0, lod_ms=0.1)
        assert risk.lod_modifier == 0.0

    def test_anomalous_lod_adds_risk(self):
        risk = compute_fantasma(bz=0, viento=0, sch_wpc=0, lod_ms=1.5)
        assert risk.lod_modifier > 0.0


class TestRiskClassification:

    def test_thresholds(self):
        assert classify_risk(0.0) == "LOW"
        assert classify_risk(4.9) == "LOW"
        assert classify_risk(5.0) == "MODERATE"
        assert classify_risk(14.9) == "MODERATE"
        assert classify_risk(15.0) == "HIGH"
        assert classify_risk(29.9) == "HIGH"
        assert classify_risk(30.0) == "CRITICAL"
        assert classify_risk(100.0) == "CRITICAL"


class TestComputeRiskFromSignals:

    def test_from_agent_dicts(self):
        signals = [
            {"bz_mean": -8.0, "plasma_speed": 500.0},
            {"schumann_activity_pct": 20.0, "kp_mean": 6.0},
        ]
        risk = compute_risk_from_signals(signals, atmospheric={"mean_pressure": 1005.0})
        assert risk.fantasma > 0
        assert risk.components["bz_nT"] == -8.0
        assert risk.components["wind_kms"] == 500.0

    def test_empty_signals_produce_low(self):
        risk = compute_risk_from_signals([])
        assert risk.risk_level == "LOW"


class TestFormatRiskReport:

    def test_contains_all_components(self):
        risk = compute_fantasma(bz=-5, viento=400, sch_wpc=0.3, pressure_hpa=1003, kp=6)
        report = format_risk_report(risk)
        assert "PRECURSOR RISK" in report
        assert "Fantasma Index" in report
        assert "Bz²" in report
        assert "Wind" in report
        assert "Schumann" in report
        assert "Pressure" in report
        assert "Kp" in report


# ── Assertivity Tracker (V46 lineage) ───────────────────────────────


class TestAssertivityTracker:

    def setup_method(self):
        self.tracker = AssertivityTracker(radius_degrees=5.0, window_days=30)

    def test_record_prediction(self):
        pred = self.tracker.record_prediction(
            latitude=17.0, longitude=-99.5,
            risk_level="HIGH", fantasma=25.0,
        )
        assert pred.latitude == 17.0
        assert pred.risk_level == "HIGH"
        assert self.tracker.prediction_count == 1

    def test_hit_within_radius(self):
        self.tracker.record_prediction(17.0, -99.5, "HIGH", 25.0)
        self.tracker.ingest_events([
            {"latitude": 16.5, "longitude": -99.0, "magnitude": 5.2, "time": time.time()},
        ])
        result = self.tracker.validate(min_magnitude=4.5)
        assert result.hits == 1
        assert result.false_alarms == 0
        assert result.hit_rate == 1.0

    def test_miss_outside_radius(self):
        self.tracker.record_prediction(17.0, -99.5, "HIGH", 25.0)
        self.tracker.ingest_events([
            {"latitude": 35.0, "longitude": -118.0, "magnitude": 6.0, "time": time.time()},
        ])
        result = self.tracker.validate(min_magnitude=4.5)
        assert result.hits == 0
        assert result.false_alarms == 1
        assert result.misses == 1

    def test_false_alarm_no_events(self):
        self.tracker.record_prediction(17.0, -99.5, "HIGH", 25.0)
        self.tracker.ingest_events([])
        result = self.tracker.validate()
        assert result.false_alarms == 1
        assert result.hits == 0

    def test_miss_no_predictions(self):
        self.tracker.ingest_events([
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 5.0, "time": time.time()},
        ])
        result = self.tracker.validate()
        assert result.misses == 1
        assert result.total_predictions == 0

    def test_euclidean_distance(self):
        dist = AssertivityTracker._euclidean_distance(0, 0, 3, 4)
        assert abs(dist - 5.0) < 0.01

    def test_multiple_predictions_and_events(self):
        self.tracker.record_prediction(17.0, -99.5, "HIGH", 25.0)
        self.tracker.record_prediction(15.0, -92.0, "MODERATE", 10.0)
        self.tracker.record_prediction(40.0, -120.0, "HIGH", 20.0)

        self.tracker.ingest_events([
            {"latitude": 16.8, "longitude": -99.2, "magnitude": 5.5, "time": time.time()},
            {"latitude": 14.5, "longitude": -91.5, "magnitude": 4.8, "time": time.time()},
        ])
        result = self.tracker.validate()
        assert result.hits == 2
        assert result.false_alarms == 1

    def test_min_magnitude_filter(self):
        self.tracker.record_prediction(17.0, -99.5, "HIGH", 25.0)
        self.tracker.ingest_events([
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 3.0, "time": time.time()},
        ])
        result = self.tracker.validate(min_magnitude=4.5)
        assert result.hits == 0
        assert result.total_events == 0

    def test_format_report(self):
        result = AssertivityResult(
            total_predictions=10, total_events=8,
            hits=6, misses=2, false_alarms=4,
            hit_rate=0.6, miss_rate=0.25, false_alarm_rate=0.4,
            evaluation_window_days=30,
        )
        report = self.tracker.format_report(result)
        assert "ASSERTIVITY REPORT" in report
        assert "60%" in report
        assert "25%" in report


# ── Molchan Baseline (modelo nulo alertar-siempre) ───────────────────


class TestMolchanBaseline:

    def setup_method(self):
        from sentinel_omega.core.precursor.baseline import AlwaysAlertBaseline
        self.baseline = AlwaysAlertBaseline(radius_degrees=5.0, window_h=72)

    def test_no_locations_zero_base_rate(self):
        rate, hits, cells = self.baseline.base_rate([], [], window_days=30)
        assert rate == 0.0
        assert cells == 0

    def test_no_events_zero_base_rate(self):
        rate, hits, cells = self.baseline.base_rate(
            [(17.0, -99.5)], [], window_days=30,
        )
        assert rate == 0.0
        assert hits == 0
        assert cells == 10   # 30d * 24h / 72h = 10 slots

    def test_event_in_one_slot(self):
        now = time.time()
        events = [
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 5.0,
             "time": now - 3600},   # último slot
        ]
        rate, hits, cells = self.baseline.base_rate(
            [(17.0, -99.5)], events, window_days=30, now=now,
        )
        assert hits == 1
        assert cells == 10
        assert abs(rate - 0.1) < 1e-9

    def test_usgs_milliseconds_accepted(self):
        now = time.time()
        events = [
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 5.0,
             "time": (now - 3600) * 1000},   # ms estilo USGS FDSN
        ]
        rate, hits, _ = self.baseline.base_rate(
            [(17.0, -99.5)], events, window_days=30, now=now,
        )
        assert hits == 1

    def test_below_magnitude_ignored(self):
        now = time.time()
        events = [
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 3.0,
             "time": now - 3600},
        ]
        rate, hits, _ = self.baseline.base_rate(
            [(17.0, -99.5)], events, window_days=30, now=now,
        )
        assert hits == 0

    def test_gain_computed(self):
        now = time.time()
        events = [
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 5.0,
             "time": now - 3600},
        ]
        res = self.baseline.evaluate(
            [(17.0, -99.5)], events, system_hit_rate=0.5,
            window_days=30, now=now,
        )
        assert res.base_rate == pytest.approx(0.1)
        assert res.gain == pytest.approx(5.0)
        assert "GANANCIA REAL" in res.veredicto

    def test_gain_undefined_without_events(self):
        res = self.baseline.evaluate(
            [(17.0, -99.5)], [], system_hit_rate=0.5, window_days=30,
        )
        assert res.gain is None
        assert "indefinida" in res.veredicto

    def test_no_gain_verdict(self):
        now = time.time()
        # Zona que tiembla en cada slot: la tasa base es 1.0
        events = [
            {"latitude": 17.0, "longitude": -99.5, "magnitude": 5.0,
             "time": now - (s * 72 + 1) * 3600}
            for s in range(10)
        ]
        res = self.baseline.evaluate(
            [(17.0, -99.5)], events, system_hit_rate=0.9,
            window_days=30, now=now,
        )
        assert res.base_rate == pytest.approx(1.0)
        assert res.gain == pytest.approx(0.9)
        assert "SIN ganancia" in res.veredicto

    def test_tracker_hook(self):
        tracker = AssertivityTracker(radius_degrees=5.0, window_days=30)
        tracker.record_prediction(17.0, -99.5, "HIGH", 25.0)
        tracker.ingest_events([
            {"latitude": 16.5, "longitude": -99.0, "magnitude": 5.2,
             "time": time.time()},
        ])
        result, baseline = tracker.validate_with_baseline()
        assert result.hit_rate == 1.0
        assert baseline.base_rate > 0
        assert baseline.gain is not None
        report = tracker.format_report(result, baseline)
        assert "Ganancia sobre modelo nulo" in report


# ── Integration: LayerRunner precursor risk ─────────────────────────


class TestGeodynamicPrecursorIntegration:

    def test_runner_computes_risk(self):
        from unittest.mock import patch, MagicMock
        from sentinel_omega.infrastructure.pipeline.layer_runners import GeodynamicLayerRunner

        runner = GeodynamicLayerRunner(enable_satellite=False)

        mock_alfa1 = {
            "omni_dataframe": pd.DataFrame({
                "bz_gsm": [-8.0, -7.0, -9.0],
                "plasma_speed": [500.0, 520.0, 480.0],
            }),
        }
        mock_beta1 = {
            "kp_series": np.array([3.0, 4.0, 5.0] * 20),
            "seismic_magnitudes": np.array([4.5, 5.0]),
            "schumann_activity": 25.0,
            "schumann_frequency": 7.83,
        }
        mock_delta = {
            "energetic_nodes": {"RegionA": 1e12, "RegionB": 5e11, "RegionC": 2e11},
            "psychosocial_index": 0.4,
            "pressure_gradient": {"mean_pressure": 1005.0, "pressure_spread": 8.0},
        }

        with (
            patch.object(runner.pipeline, "fetch_alfa1_data", return_value=mock_alfa1),
            patch.object(runner.pipeline, "fetch_beta1_data", return_value=mock_beta1),
            patch.object(runner.pipeline, "fetch_delta_data", return_value=mock_delta),
            patch.object(runner.pipeline, "fetch_jupiter_data", return_value={}),
        ):
            consensus = runner.run()

        assert runner.last_risk is not None
        assert runner.last_risk.fantasma > 0
        assert runner.last_risk.components["bz_nT"] < 0
        assert consensus.precursor_risk is runner.last_risk

    def test_runner_risk_with_empty_data(self):
        from unittest.mock import patch
        from sentinel_omega.infrastructure.pipeline.layer_runners import GeodynamicLayerRunner

        runner = GeodynamicLayerRunner(enable_satellite=False)

        with (
            patch.object(runner.pipeline, "fetch_alfa1_data", return_value={}),
            patch.object(runner.pipeline, "fetch_beta1_data", return_value={}),
            patch.object(runner.pipeline, "fetch_delta_data", return_value={}),
            patch.object(runner.pipeline, "fetch_jupiter_data", return_value={}),
        ):
            consensus = runner.run()

        assert runner.last_risk is not None
        assert runner.last_risk.fantasma == 0.0
        assert runner.last_risk.risk_level == "LOW"


# ── Precursor Types Registry ────────────────────────────────────────


class TestPrecursorTypes:

    def test_all_types_have_profiles(self):
        for pt in PrecursorType:
            assert pt in PRECURSOR_PROFILES

    def test_all_types_have_display_names(self):
        for pt in PrecursorType:
            assert pt in PRECURSOR_DISPLAY_NAMES

    def test_profile_has_required_fields(self):
        for pt, profile in PRECURSOR_PROFILES.items():
            assert profile.tipo == pt
            assert profile.validation_window_hours > 0
            assert len(profile.variables) > 0

    def test_get_profile(self):
        p = get_profile(PrecursorType.FANTASMA)
        assert p.tipo == PrecursorType.FANTASMA
        assert "bz_nT" in p.variables


class TestBlueJetDetection:

    def test_thunderstorm_hot(self):
        assert detect_blue_jet(temp_c=30.0, weather_id=210) is True

    def test_thunderstorm_cold(self):
        assert detect_blue_jet(temp_c=15.0, weather_id=210) is False

    def test_clear_sky_hot(self):
        assert detect_blue_jet(temp_c=35.0, weather_id=800) is False

    def test_boundary_weather_id(self):
        assert detect_blue_jet(temp_c=30.0, weather_id=200) is True
        assert detect_blue_jet(temp_c=30.0, weather_id=232) is True
        assert detect_blue_jet(temp_c=30.0, weather_id=199) is False
        assert detect_blue_jet(temp_c=30.0, weather_id=233) is False


class TestNieblaTuleDetection:

    def test_dense_fog(self):
        assert detect_niebla_tule(humidity_pct=95.0, visibility_m=500.0) is True

    def test_normal_conditions(self):
        assert detect_niebla_tule(humidity_pct=60.0, visibility_m=10000.0) is False

    def test_high_humidity_good_visibility(self):
        assert detect_niebla_tule(humidity_pct=95.0, visibility_m=5000.0) is False

    def test_low_visibility_low_humidity(self):
        assert detect_niebla_tule(humidity_pct=50.0, visibility_m=500.0) is False


class TestSilentTriggerDetection:

    def test_all_low_kp(self):
        kp = [0.5, 1.0, 0.3, 1.2, 0.8, 0.5, 1.0, 0.3, 1.2, 0.8, 1.5, 0.7]
        assert detect_silent_trigger(kp) is True

    def test_one_high_kp(self):
        kp = [0.5, 1.0, 0.3, 1.2, 0.8, 0.5, 1.0, 3.5, 1.2, 0.8, 1.5, 0.7]
        assert detect_silent_trigger(kp) is False

    def test_insufficient_data(self):
        assert detect_silent_trigger([1.0, 0.5, 0.3]) is False


class TestSeismicClusterDetection:

    def test_cluster_detected(self):
        assert detect_seismic_cluster(15) is True

    def test_below_threshold(self):
        assert detect_seismic_cluster(5) is False

    def test_exact_threshold(self):
        assert detect_seismic_cluster(10) is True


class TestVolcanicPrecursor:

    def test_volcanic_detected(self):
        assert detect_volcanic_precursor(so2_mass=150.0, seismic_count=5) is True

    def test_no_so2(self):
        assert detect_volcanic_precursor(so2_mass=20.0, seismic_count=5) is False

    def test_no_seismicity(self):
        assert detect_volcanic_precursor(so2_mass=150.0, seismic_count=1) is False


class TestSpriteRojoDetection:

    def test_severe_storm_hot_low_pressure_cloudy(self):
        assert detect_sprite_rojo(weather_id=211, temp_c=32.0, pressure_hpa=1000.0, clouds_pct=100) is True

    def test_no_thunderstorm(self):
        assert detect_sprite_rojo(weather_id=800, temp_c=32.0, pressure_hpa=1000.0, clouds_pct=100) is False

    def test_too_cold(self):
        assert detect_sprite_rojo(weather_id=211, temp_c=25.0, pressure_hpa=1000.0, clouds_pct=100) is False

    def test_pressure_too_high(self):
        assert detect_sprite_rojo(weather_id=211, temp_c=32.0, pressure_hpa=1010.0, clouds_pct=100) is False

    def test_not_enough_clouds(self):
        assert detect_sprite_rojo(weather_id=211, temp_c=32.0, pressure_hpa=1000.0, clouds_pct=50) is False


class TestHurricaneDetection:

    def test_cat1_nearby(self):
        assert detect_hurricane_proximity(category=1, distance_deg=5.0) is True

    def test_tropical_storm_not_hurricane(self):
        assert detect_hurricane_proximity(category=0, distance_deg=5.0) is False

    def test_too_far(self):
        assert detect_hurricane_proximity(category=3, distance_deg=15.0) is False

    def test_cat5_in_range(self):
        assert detect_hurricane_proximity(category=5, distance_deg=2.0) is True


class TestTsunamiDetection:

    def test_m7_shallow(self):
        assert detect_tsunami_potential(magnitude=7.5, depth_km=20.0) is True

    def test_m6_shallow(self):
        assert detect_tsunami_potential(magnitude=6.8, depth_km=20.0) is False

    def test_m7_deep(self):
        assert detect_tsunami_potential(magnitude=7.5, depth_km=100.0) is False


class TestMuroCincoEventos:

    def _make_detection(self, tipo, confidence=0.8):
        from sentinel_omega.core.precursor.scanner import PrecursorDetection
        return PrecursorDetection(
            tipo=tipo,
            display_name="test",
            station="test",
            lat=None, lon=None,
            confidence=confidence,
        )

    def test_no_detections_no_breach(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        result = muro.evaluate([])
        assert result.walls_active == 0
        assert result.muro_breach is False
        assert result.risk_label == "NORMAL"

    def test_single_wall_no_breach(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [self._make_detection(PrecursorType.TORMENTA_SOLAR)]
        result = muro.evaluate(detections)
        assert result.walls_active == 1
        assert result.muro_breach is False
        assert result.risk_label == "BAJO"

    def test_two_walls_no_breach(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.TORMENTA_SOLAR),
            self._make_detection(PrecursorType.BLUE_JET),
        ]
        result = muro.evaluate(detections)
        assert result.walls_active == 2
        assert result.muro_breach is False
        assert result.risk_label == "MODERADO"

    def test_three_walls_breach(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.SEISMIC_CLUSTER),
            self._make_detection(PrecursorType.BLUE_JET),
            self._make_detection(PrecursorType.TORMENTA_SOLAR),
        ]
        result = muro.evaluate(detections)
        assert result.walls_active == 3
        assert result.muro_breach is True
        assert result.risk_label == "ALTO"

    def test_four_walls_critical(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.VOLCANICO),
            self._make_detection(PrecursorType.SPRITE_ROJO),
            self._make_detection(PrecursorType.HURACAN),
            self._make_detection(PrecursorType.SCHUMANN),
        ]
        result = muro.evaluate(detections)
        assert result.walls_active == 4
        assert result.muro_breach is True
        assert result.risk_label == "CRÍTICO"

    def test_five_walls_all_active(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.FANTASMA),
            self._make_detection(PrecursorType.NIEBLA_TULE),
            self._make_detection(PrecursorType.TSUNAMI),
            self._make_detection(PrecursorType.SILENT_TRIGGER),
            self._make_detection(PrecursorType.CORRELACION_FINANCIERA),
        ]
        result = muro.evaluate(detections)
        assert result.walls_active == 5
        assert result.muro_breach is True

    def test_correlation_score(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.SEISMIC_CLUSTER, confidence=0.9),
            self._make_detection(PrecursorType.BLUE_JET, confidence=0.7),
        ]
        result = muro.evaluate(detections)
        assert result.correlation_score > 0
        assert result.correlation_score < 1.0

    def test_same_wall_multiple_precursors(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.TORMENTA_SOLAR, confidence=0.9),
            self._make_detection(PrecursorType.SCHUMANN, confidence=0.7),
            self._make_detection(PrecursorType.SILENT_TRIGGER, confidence=0.6),
        ]
        result = muro.evaluate(detections)
        assert result.walls_active == 1
        solar_wall = [w for w in result.wall_statuses if w.name == "SOLAR/GEOMAGNÉTICO"][0]
        assert solar_wall.precursor_count == 3
        assert solar_wall.max_confidence == 0.9

    def test_format_muro_report(self):
        from sentinel_omega.core.precursor.muro_cinco_eventos import MuroCincoEventos, format_muro_report
        muro = MuroCincoEventos()
        detections = [
            self._make_detection(PrecursorType.VOLCANICO),
            self._make_detection(PrecursorType.BLUE_JET),
            self._make_detection(PrecursorType.HURACAN),
        ]
        result = muro.evaluate(detections)
        report = format_muro_report(result)
        assert "MURO DE LOS 5 EVENTOS" in report
        assert "GEOFÍSICO" in report
        assert "ATMOSFÉRICO" in report
        assert "OCEÁNICO" in report


class TestPrecursorScanner:

    def _make_scanner(self):
        from sentinel_omega.core.precursor.scanner import PrecursorScanner
        return PrecursorScanner()

    def test_no_detections_on_calm_data(self):
        scanner = self._make_scanner()
        alfa1 = {}
        beta1 = {"kp_series": np.array([3.0] * 24), "schumann_frequency": 7.83, "schumann_activity": 100.0}
        delta = {"atmospheric_readings": [
            {"station": "tlaxcala", "lat": 19.31, "lon": -98.24,
             "temp_c": 20.0, "weather_id": 800, "pressure_hpa": 1015.0,
             "humidity_pct": 50.0, "visibility_m": 10000},
        ], "air_quality": {"so2": 5.0}}
        detections = scanner.scan(alfa1, beta1, delta)
        assert len(detections) == 0

    def test_blue_jet_detection(self):
        scanner = self._make_scanner()
        delta = {"atmospheric_readings": [
            {"station": "tlaxcala", "lat": 19.31, "lon": -98.24,
             "temp_c": 30.0, "weather_id": 211, "pressure_hpa": 1005.0,
             "humidity_pct": 60.0, "visibility_m": 8000},
        ]}
        detections = scanner.scan({}, {}, delta)
        assert len(detections) == 1
        assert detections[0].tipo == PrecursorType.BLUE_JET
        assert detections[0].station == "tlaxcala"
        assert detections[0].confidence >= 0.7

    def test_niebla_tule_detection(self):
        scanner = self._make_scanner()
        delta = {"atmospheric_readings": [
            {"station": "oaxaca", "lat": 17.07, "lon": -96.72,
             "temp_c": 15.0, "weather_id": 741, "pressure_hpa": 1012.0,
             "humidity_pct": 96.0, "visibility_m": 400},
        ]}
        detections = scanner.scan({}, {}, delta)
        assert len(detections) == 1
        assert detections[0].tipo == PrecursorType.NIEBLA_TULE
        assert detections[0].values["visibility_m"] == 400

    def test_silent_trigger_detection(self):
        scanner = self._make_scanner()
        beta1 = {"kp_series": np.array([0.5] * 24)}
        detections = scanner.scan({}, beta1, {})
        assert len(detections) == 1
        assert detections[0].tipo == PrecursorType.SILENT_TRIGGER

    def test_seismic_cluster_detection(self):
        scanner = self._make_scanner()
        beta1 = {"seismic_magnitudes": np.array([4.5, 4.2, 4.8, 4.1, 4.3, 5.0, 4.7, 4.4, 4.6, 4.9, 5.1])}
        detections = scanner.scan({}, beta1, {})
        cluster = [d for d in detections if d.tipo == PrecursorType.SEISMIC_CLUSTER]
        assert len(cluster) == 1
        assert cluster[0].values["event_count"] >= 10

    def test_volcanic_detection(self):
        scanner = self._make_scanner()
        beta1 = {"seismic_magnitudes": np.array([3.5, 3.2, 4.0, 3.8, 3.1])}
        delta = {
            "air_quality": {"so2": 250.0},
            "atmospheric_readings": [
                {"station": "colima", "lat": 19.24, "lon": -103.72,
                 "temp_c": 22.0, "weather_id": 800, "pressure_hpa": 1010.0,
                 "humidity_pct": 60.0, "visibility_m": 5000},
            ],
        }
        detections = scanner.scan({}, beta1, delta)
        volcanic = [d for d in detections if d.tipo == PrecursorType.VOLCANICO]
        assert len(volcanic) == 1
        assert volcanic[0].values["so2_mass"] == 250.0

    def test_schumann_excitation(self):
        scanner = self._make_scanner()
        beta1 = {"schumann_frequency": 9.5, "schumann_activity": 250.0}
        detections = scanner.scan({}, beta1, {})
        sch = [d for d in detections if d.tipo == PrecursorType.SCHUMANN]
        assert len(sch) == 1
        assert sch[0].values["deviation_hz"] > 1.0

    def test_tormenta_solar_detection(self):
        scanner = self._make_scanner()
        omni_df = pd.DataFrame({
            "bz_gsm": [-25.0, -22.0, -28.0],
            "plasma_speed": [700.0, 680.0, 720.0],
        })
        alfa1 = {"omni_dataframe": omni_df}
        beta1 = {"kp_series": np.array([6.0, 7.0, 5.5, 6.5])}
        detections = scanner.scan(alfa1, beta1, {})
        storm = [d for d in detections if d.tipo == PrecursorType.TORMENTA_SOLAR]
        assert len(storm) == 1
        assert storm[0].confidence >= 0.7

    def test_perturbacion_geomagnetica_moderate(self):
        scanner = self._make_scanner()
        omni_df = pd.DataFrame({
            "bz_gsm": [-7.0, -6.0, -8.0],
            "plasma_speed": [400.0, 380.0, 420.0],
        })
        alfa1 = {"omni_dataframe": omni_df}
        beta1 = {"kp_series": np.array([4.0, 3.5, 4.5])}
        detections = scanner.scan(alfa1, beta1, {})
        geo = [d for d in detections if d.tipo == PrecursorType.PERTURBACION_GEOMAGNETICA]
        assert len(geo) == 1

    def test_perturbacion_excluded_when_tormenta(self):
        """If Bz <= -10 and Kp >= 5, it's a tormenta, not a perturbacion."""
        scanner = self._make_scanner()
        omni_df = pd.DataFrame({
            "bz_gsm": [-15.0, -12.0],
            "plasma_speed": [600.0, 580.0],
        })
        alfa1 = {"omni_dataframe": omni_df}
        beta1 = {"kp_series": np.array([5.5, 6.0])}
        detections = scanner.scan(alfa1, beta1, {})
        geo = [d for d in detections if d.tipo == PrecursorType.PERTURBACION_GEOMAGNETICA]
        assert len(geo) == 0
        storm = [d for d in detections if d.tipo == PrecursorType.TORMENTA_SOLAR]
        assert len(storm) == 1

    def test_multiple_simultaneous_precursors(self):
        scanner = self._make_scanner()
        omni_df = pd.DataFrame({
            "bz_gsm": [-25.0, -22.0],
            "plasma_speed": [700.0, 680.0],
        })
        alfa1 = {"omni_dataframe": omni_df}
        beta1 = {
            "kp_series": np.array([6.0, 7.0, 5.5, 6.5]),
            "schumann_frequency": 9.5,
            "schumann_activity": 250.0,
        }
        delta = {"atmospheric_readings": [
            {"station": "tlaxcala", "lat": 19.31, "lon": -98.24,
             "temp_c": 30.0, "weather_id": 211, "pressure_hpa": 1005.0,
             "humidity_pct": 60.0, "visibility_m": 8000},
        ]}
        detections = scanner.scan(alfa1, beta1, delta)
        types = {d.tipo for d in detections}
        assert PrecursorType.TORMENTA_SOLAR in types
        assert PrecursorType.SCHUMANN in types
        assert PrecursorType.BLUE_JET in types
        assert len(detections) >= 3


class TestScannerSpriteRojo:

    def _make_scanner(self):
        from sentinel_omega.core.precursor.scanner import PrecursorScanner
        return PrecursorScanner()

    def test_sprite_rojo_detected(self):
        scanner = self._make_scanner()
        delta = {"atmospheric_readings": [
            {"station": "guerrero", "lat": 17.55, "lon": -99.50,
             "temp_c": 33.0, "weather_id": 211, "pressure_hpa": 998.0,
             "humidity_pct": 70.0, "visibility_m": 5000, "clouds_pct": 95},
        ]}
        detections = scanner.scan({}, {}, delta)
        sprites = [d for d in detections if d.tipo == PrecursorType.SPRITE_ROJO]
        assert len(sprites) == 1
        assert sprites[0].station == "guerrero"

    def test_sprite_not_detected_clear_sky(self):
        scanner = self._make_scanner()
        delta = {"atmospheric_readings": [
            {"station": "guerrero", "lat": 17.55, "lon": -99.50,
             "temp_c": 33.0, "weather_id": 211, "pressure_hpa": 998.0,
             "humidity_pct": 70.0, "visibility_m": 5000, "clouds_pct": 30},
        ]}
        detections = scanner.scan({}, {}, delta)
        sprites = [d for d in detections if d.tipo == PrecursorType.SPRITE_ROJO]
        assert len(sprites) == 0


class TestScannerHurricane:

    def _make_scanner(self):
        from sentinel_omega.core.precursor.scanner import PrecursorScanner
        return PrecursorScanner()

    def test_hurricane_detected(self):
        scanner = self._make_scanner()
        hurricane_data = {
            "active_cyclones": [{
                "name": "Otis", "category": 5, "lat": 16.0, "lon": -99.0,
                "max_wind_kt": 165, "pressure_mb": 923, "distance_deg": 3.0,
            }],
        }
        detections = scanner.scan({}, {}, {}, hurricane_data=hurricane_data)
        hurr = [d for d in detections if d.tipo == PrecursorType.HURACAN]
        assert len(hurr) == 1
        assert hurr[0].confidence >= 0.8

    def test_no_hurricane_data(self):
        scanner = self._make_scanner()
        detections = scanner.scan({}, {}, {}, hurricane_data={})
        hurr = [d for d in detections if d.tipo == PrecursorType.HURACAN]
        assert len(hurr) == 0


class TestScannerTsunami:

    def _make_scanner(self):
        from sentinel_omega.core.precursor.scanner import PrecursorScanner
        return PrecursorScanner()

    def test_tsunamigenic_quake(self):
        scanner = self._make_scanner()
        beta1 = {"seismic_magnitudes": np.array([7.8, 4.5, 5.2, 3.1])}
        delta = {"max_quake_depth_km": 15.0}
        detections = scanner.scan({}, beta1, delta)
        tsunami = [d for d in detections if d.tipo == PrecursorType.TSUNAMI]
        assert len(tsunami) == 1
        assert tsunami[0].values["magnitude"] == 7.8

    def test_no_tsunami_m6(self):
        scanner = self._make_scanner()
        beta1 = {"seismic_magnitudes": np.array([6.5, 5.2, 3.1])}
        delta = {"max_quake_depth_km": 15.0}
        detections = scanner.scan({}, beta1, delta)
        tsunami = [d for d in detections if d.tipo == PrecursorType.TSUNAMI]
        assert len(tsunami) == 0


class TestScannerFinancialCorrelation:

    def _make_scanner(self):
        from sentinel_omega.core.precursor.scanner import PrecursorScanner
        return PrecursorScanner()

    def test_extreme_fear_plus_vix(self):
        scanner = self._make_scanner()
        financial = {"fear_greed": 10, "vix": 40.0, "btc_change_pct": -2.0, "market_signal": "neutral"}
        detections = scanner.scan({}, {}, {}, financial_data=financial)
        fin = [d for d in detections if d.tipo == PrecursorType.CORRELACION_FINANCIERA]
        assert len(fin) == 1
        assert fin[0].values["fear_greed"] == 10

    def test_triple_signal(self):
        scanner = self._make_scanner()
        financial = {"fear_greed": 8, "vix": 45.0, "btc_change_pct": -15.0, "market_signal": "bearish"}
        detections = scanner.scan({}, {}, {}, financial_data=financial)
        fin = [d for d in detections if d.tipo == PrecursorType.CORRELACION_FINANCIERA]
        assert len(fin) == 1
        assert fin[0].values["active_financial_signals"] == 4

    def test_calm_market_no_detection(self):
        scanner = self._make_scanner()
        financial = {"fear_greed": 50, "vix": 15.0, "btc_change_pct": 2.0, "market_signal": "bullish"}
        detections = scanner.scan({}, {}, {}, financial_data=financial)
        fin = [d for d in detections if d.tipo == PrecursorType.CORRELACION_FINANCIERA]
        assert len(fin) == 0


class TestTelegramPrecursorFormat:

    def test_format_precursor_alert(self):
        from sentinel_omega.infrastructure.api.telegram import format_precursor_alert
        msg = format_precursor_alert(
            precursor_type="BLUE_JET",
            display_name="Blue Jet (Fuga Ionosférica)",
            value=1.0,
            details="Thunderstorm detected at Tlaxcala node",
            lat=19.31, lon=-98.24,
            lugar="Tlaxcala",
        )
        assert "SENTINEL OMEGA — PRECURSOR" in msg
        assert "Blue Jet" in msg
        assert "72h" in msg
        assert "48h" in msg
        assert "Tlaxcala" in msg


# ── Precipitation potential (Schumann-modular formula) ───────────────────────


class TestPrecipitacionPotencial:
    """
    Formula: Π_i(t) = μ_i(t) · (Φ_i(t) mod Φ_S(t))
      μ_i  = humidity_pct / 100
      Φ_i  = temp_c * (clouds_pct / 100) + 273.15   (K-scale)
      Φ_S  = schumann_hz * 10.0                      (K-scale)
    Threshold: 30.0
    """

    def test_formula_clear_day_below_threshold(self):
        """Low humidity, few clouds → small residual × low μ → not triggered."""
        pi = compute_precipitacion_potencial(
            humidity_pct=50.0, temp_c=20.0, clouds_pct=10.0, schumann_hz=7.83
        )
        assert pi < 30.0
        assert not detect_precipitacion_potencial(50.0, 20.0, 10.0, 7.83)

    def test_formula_heavy_rain_triggered(self):
        """High humidity, heavy clouds, warm → large Π_i → triggered."""
        pi = compute_precipitacion_potencial(
            humidity_pct=85.0, temp_c=28.0, clouds_pct=90.0, schumann_hz=8.2
        )
        assert pi >= 30.0
        assert detect_precipitacion_potencial(85.0, 28.0, 90.0, 8.2)

    def test_formula_overcast_triggered(self):
        """Overcast rain scenario: humidity=90, clouds=95."""
        pi = compute_precipitacion_potencial(
            humidity_pct=90.0, temp_c=18.0, clouds_pct=95.0, schumann_hz=7.9
        )
        assert pi >= 30.0

    def test_dry_desert_not_triggered(self):
        """Very low humidity, minimal clouds → no precipitation."""
        assert not detect_precipitacion_potencial(15.0, 35.0, 5.0, 7.83)

    def test_zero_schumann_returns_zero(self):
        """Guard: Φ_S ≤ 0 must not raise and must return 0."""
        pi = compute_precipitacion_potencial(90.0, 25.0, 100.0, schumann_hz=0.0)
        assert pi == 0.0

    def test_custom_threshold(self):
        """detect_ respects the threshold parameter."""
        pi = compute_precipitacion_potencial(70.0, 22.0, 60.0, 7.83)
        assert detect_precipitacion_potencial(70.0, 22.0, 60.0, 7.83, threshold=pi - 0.01)
        assert not detect_precipitacion_potencial(70.0, 22.0, 60.0, 7.83, threshold=pi + 0.01)

    def test_profile_registered(self):
        """PRECIPITACION must appear in PRECURSOR_PROFILES and PRECURSOR_DISPLAY_NAMES."""
        assert PrecursorType.PRECIPITACION in PRECURSOR_PROFILES
        assert PrecursorType.PRECIPITACION in PRECURSOR_DISPLAY_NAMES
        profile = PRECURSOR_PROFILES[PrecursorType.PRECIPITACION]
        assert "humidity_pct" in profile.variables
        assert "schumann_hz" in profile.variables
        assert "pi_i" in profile.variables

    def test_humidity_drives_result(self):
        """Doubling humidity (below saturation) roughly doubles Π_i."""
        pi_low = compute_precipitacion_potencial(40.0, 25.0, 80.0, 7.83)
        pi_high = compute_precipitacion_potencial(80.0, 25.0, 80.0, 7.83)
        assert pi_low > 0, "baseline Π_i must be positive for this ratio test"
        assert abs(pi_high / pi_low - 2.0) < 0.01


class TestScannerPrecipitacion:

    def _make_scanner(self):
        from sentinel_omega.core.precursor.scanner import PrecursorScanner
        return PrecursorScanner()

    def _beta1_with_schumann(self, hz: float = 8.2) -> dict:
        return {"schumann_frequency": hz, "schumann_activity": 150.0}

    def test_heavy_rain_reading_detected(self):
        scanner = self._make_scanner()
        atm = [{"station": "Xalapa", "lat": 19.5, "lon": -96.9,
                "humidity_pct": 88.0, "temp_c": 26.0, "clouds_pct": 92.0,
                "pressure_hpa": 1010.0, "weather_id": 800}]
        delta = {"atmospheric_readings": atm, "air_quality": {}}
        detections = scanner.scan({}, self._beta1_with_schumann(8.2), delta)
        prec = [d for d in detections if d.tipo == PrecursorType.PRECIPITACION]
        assert len(prec) == 1
        assert prec[0].station == "Xalapa"
        assert prec[0].values["pi_i"] >= 30.0
        assert prec[0].confidence >= 0.5

    def test_clear_day_no_detection(self):
        scanner = self._make_scanner()
        atm = [{"station": "node_A", "humidity_pct": 45.0, "temp_c": 22.0,
                "clouds_pct": 10.0, "pressure_hpa": 1015.0, "weather_id": 800}]
        delta = {"atmospheric_readings": atm, "air_quality": {}}
        detections = scanner.scan({}, self._beta1_with_schumann(7.83), delta)
        prec = [d for d in detections if d.tipo == PrecursorType.PRECIPITACION]
        assert len(prec) == 0

    def test_missing_schumann_no_detection(self):
        """If beta1 does not supply schumann_frequency, no precipitation scan."""
        scanner = self._make_scanner()
        atm = [{"station": "node_B", "humidity_pct": 95.0, "temp_c": 28.0,
                "clouds_pct": 100.0, "pressure_hpa": 1005.0, "weather_id": 500}]
        delta = {"atmospheric_readings": atm, "air_quality": {}}
        detections = scanner.scan({}, {}, delta)
        prec = [d for d in detections if d.tipo == PrecursorType.PRECIPITACION]
        assert len(prec) == 0

    def test_multiple_readings_multiple_detections(self):
        """Each rainy reading produces its own PrecursorDetection."""
        scanner = self._make_scanner()
        atm = [
            {"station": "A", "humidity_pct": 90.0, "temp_c": 25.0, "clouds_pct": 90.0,
             "pressure_hpa": 1008.0, "weather_id": 500},
            {"station": "B", "humidity_pct": 85.0, "temp_c": 27.0, "clouds_pct": 88.0,
             "pressure_hpa": 1007.0, "weather_id": 500},
        ]
        delta = {"atmospheric_readings": atm, "air_quality": {}}
        detections = scanner.scan({}, self._beta1_with_schumann(8.0), delta)
        prec = [d for d in detections if d.tipo == PrecursorType.PRECIPITACION]
        assert len(prec) == 2

    def test_high_pi_boosts_confidence(self):
        """A very high Π_i (≥ 45) should push confidence above 0.7."""
        scanner = self._make_scanner()
        atm = [{"station": "Veracruz", "lat": 19.18, "lon": -96.14,
                "humidity_pct": 92.0, "temp_c": 30.0, "clouds_pct": 95.0,
                "pressure_hpa": 1005.0, "weather_id": 500}]
        delta = {"atmospheric_readings": atm, "air_quality": {}}
        detections = scanner.scan({}, self._beta1_with_schumann(8.2), delta)
        prec = [d for d in detections if d.tipo == PrecursorType.PRECIPITACION]
        if prec:
            assert prec[0].confidence >= 0.70
