"""Tests for data pipeline, layer runner, and legacy data loader."""

import sqlite3
import tempfile
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from sentinel_omega.infrastructure.pipeline.data_pipeline import GeodynamicPipeline
from sentinel_omega.infrastructure.pipeline.layer_runners import GeodynamicLayerRunner
from sentinel_omega.infrastructure.pipeline.legacy_loader import LegacyDataLoader
from sentinel_omega.core.shared.agent_base import SignalType


# ── Helpers ────────────────────────────────────────────────────────


def _mock_kp_df():
    return pd.DataFrame({
        "time_tag": pd.date_range("2024-01-01", periods=100, freq="3h"),
        "kp_index": np.random.uniform(0, 5, 100),
    })


def _mock_mag_df():
    return pd.DataFrame({
        "time_tag": pd.date_range("2024-01-01", periods=100, freq="1min"),
        "bz_gsm": np.random.uniform(-10, 5, 100),
    })


def _mock_wind_df():
    return pd.DataFrame({
        "time_tag": pd.date_range("2024-01-01", periods=100, freq="1min"),
        "proton_speed": np.random.uniform(300, 600, 100),
        "proton_density": np.random.uniform(2, 10, 100),
    })


def _mock_eq_df():
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=20, freq="1D"),
        "magnitude": np.random.uniform(4.0, 7.0, 20),
        "place": [f"City {i}, Region {i % 5}" for i in range(20)],
        "depth_km": np.random.uniform(5, 100, 20),
        "longitude": np.random.uniform(-180, 180, 20),
        "latitude": np.random.uniform(-90, 90, 20),
        "type": ["earthquake"] * 20,
    })


def _mock_binance_df():
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=90, freq="1D"),
        "open": np.random.uniform(40000, 50000, 90),
        "high": np.random.uniform(40000, 50000, 90),
        "low": np.random.uniform(40000, 50000, 90),
        "close": np.random.uniform(40000, 50000, 90),
        "volume": np.random.uniform(1000, 5000, 90),
    })


def _mock_yahoo_df():
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=200, freq="1D"),
        "open": np.random.uniform(140, 180, 200),
        "high": np.random.uniform(140, 180, 200),
        "low": np.random.uniform(140, 180, 200),
        "close": np.random.uniform(140, 180, 200),
        "volume": np.random.uniform(50e6, 100e6, 200),
    })


# ── Geodynamic Pipeline ───────────────────────────────────────────


class TestGeodynamicPipeline:

    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_solar_wind")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_mag_field")
    def test_alfa1_data(self, mock_mag, mock_wind):
        mock_mag.return_value = _mock_mag_df()
        mock_wind.return_value = _mock_wind_df()

        pipe = GeodynamicPipeline()
        data = pipe.fetch_alfa1_data()
        assert "omni_dataframe" in data
        df = data["omni_dataframe"]
        assert "bz_gsm" in df.columns

    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.compute_lunar_phase_series")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_lod_series")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_schumann_resonance")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_earthquakes")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_kp_index")
    def test_beta1_data(self, mock_kp, mock_eq, mock_schumann, mock_lod, mock_lunar):
        mock_kp.return_value = _mock_kp_df()
        mock_eq.return_value = _mock_eq_df()
        mock_schumann.return_value = (8.12, 3.5)
        mock_lod.return_value = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=90, freq="1D"),
            "lod_ms": np.random.uniform(-0.5, 1.5, 90),
        })
        mock_lunar.return_value = np.linspace(0, 1, 30)

        pipe = GeodynamicPipeline()
        data = pipe.fetch_beta1_data()
        assert "kp_series" in data
        assert len(data["kp_series"]) == 100
        assert "seismic_magnitudes" in data
        assert data["schumann_frequency"] == 8.12
        assert data["schumann_activity"] == 3.5
        assert "lod_ms" in data
        assert len(data["lod_ms"]) == 90
        assert "lunar_phase" in data
        assert len(data["lunar_phase"]) == 30

    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_air_quality")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_monitoring_network")
    def test_beta2_data(self, mock_owm, mock_aq):
        from sentinel_omega.infrastructure.api.openweathermap import AtmosphericReading
        mock_owm.return_value = [
            AtmosphericReading("tlaxcala", 19.31, -98.24, 1005.0, 18.0, 65.0, 8000, 3.2, 180, 40),
            AtmosphericReading("oaxaca", 17.07, -96.72, 1012.0, 28.0, 70.0, 10000, 2.1, 200, 30),
        ]
        mock_aq.return_value = {"co": 250.0, "so2": 25.0, "no2": 10.0, "pm2_5": 12.0, "pm10": 20.0, "o3": 60.0, "aqi": 2}

        pipe = GeodynamicPipeline()
        data = pipe.fetch_beta2_data()
        assert "pressure_gradient" in data
        assert data["pressure_gradient"]["mean_pressure"] < 1013.0
        assert "air_quality" in data
        assert data["air_quality"]["so2"] == 25.0
        assert "atmospheric_readings" in data
        assert len(data["atmospheric_readings"]) == 2

    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_sector_etfs")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_vix")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_yield_spread")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_binance_klines")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_coingecko_dominance")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_fear_greed_index")
    def test_delta_data(self, mock_fg, mock_dom, mock_klines, mock_spread, mock_vix, mock_sectors):
        mock_fg.return_value = {"value": 25, "classification": "Extreme Fear"}
        mock_dom.return_value = {"btc": 54.0, "eth": 17.0}
        mock_klines.return_value = _mock_binance_df()
        mock_spread.return_value = 1.5
        mock_vix.return_value = pd.DataFrame({"close": [22.0], "volume": [1e6]})
        mock_sectors.return_value = {
            "XLK": pd.DataFrame({"close": [200.0], "volume": [5e6]}),
            "XLF": pd.DataFrame({"close": [40.0], "volume": [8e6]}),
        }

        pipe = GeodynamicPipeline()
        data = pipe.fetch_delta_data()
        assert data["fear_greed"] == 25.0
        assert data["btc_dominance"] == pytest.approx(0.54)
        assert data["vix"] == pytest.approx(22.0)
        assert data["yield_spread"] == 1.5
        assert len(data["sector_market_caps"]) == 2

    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_mag_field")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_solar_wind")
    def test_alfa1_no_data(self, mock_wind, mock_mag):
        mock_mag.return_value = None
        mock_wind.return_value = None

        pipe = GeodynamicPipeline()
        data = pipe.fetch_alfa1_data()
        assert data == {}


# ── Layer Runner ──────────────────────────────────────────────────


class TestLayerRunner:

    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.GeodynamicPipeline.fetch_jupiter_data", return_value={})
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_sector_etfs")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_vix")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_yield_spread")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_binance_klines")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_coingecko_dominance")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_air_quality")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_monitoring_network")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.compute_lunar_phase_series")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_lod_series")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_schumann_resonance")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_fear_greed_index")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_earthquakes")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_kp_index")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_solar_wind")
    @patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_mag_field")
    def test_geodynamic_runner(
        self, mock_mag, mock_wind, mock_kp, mock_eq, mock_fg,
        mock_schumann, mock_lod, mock_lunar, mock_owm, mock_aq,
        mock_dom, mock_klines, mock_spread, mock_vix, mock_sectors,
        mock_jupiter,
    ):
        mock_mag.return_value = _mock_mag_df()
        mock_wind.return_value = _mock_wind_df()
        mock_kp.return_value = _mock_kp_df()
        mock_eq.return_value = _mock_eq_df()
        mock_fg.return_value = {"value": 50, "classification": "Neutral"}
        mock_schumann.return_value = (7.95, 1.2)
        mock_lod.return_value = pd.DataFrame({
            "date": pd.date_range("2024-01-01", periods=30, freq="1D"),
            "lod_ms": np.random.uniform(0.0, 1.0, 30),
        })
        mock_lunar.return_value = np.linspace(0, 1, 30)
        mock_owm.return_value = []
        mock_aq.return_value = None
        mock_dom.return_value = {"btc": 54.0}
        mock_klines.return_value = _mock_binance_df()
        mock_spread.return_value = 0.8
        mock_vix.return_value = pd.DataFrame({"close": [18.0], "volume": [1e6]})
        mock_sectors.return_value = {
            "XLK": pd.DataFrame({"close": [200.0], "volume": [5e6]}),
        }

        runner = GeodynamicLayerRunner(enable_satellite=False)
        consensus = runner.run()
        assert consensus is not None
        assert consensus.final_signal in SignalType


# ── Legacy Data Loader ─────────────────────────────────────────────


class TestLegacyDataLoader:

    @pytest.fixture
    def cerebro_db(self, tmp_path):
        db_path = tmp_path / "cerebro.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE historicos (
                id INTEGER PRIMARY KEY,
                fecha TEXT,
                sismo_max_mag REAL,
                promedio_kp REAL,
                promedio_tomsk REAL,
                so2_mass REAL,
                co_flux REAL,
                temp_max REAL,
                presion_atm REAL
            )
        """)
        for i in range(100):
            conn.execute(
                "INSERT INTO historicos VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (i, f"2024-01-{(i % 28) + 1:02d}", 4.0 + i * 0.01,
                 2.0 + i * 0.01, 7.83, 0.0, 0.0, 20.0, 1013.0),
            )
        conn.execute("""
            CREATE TABLE bitacora (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                fecha TEXT,
                v_fantasma REAL,
                kp REAL,
                bz REAL,
                tomsk_val REAL,
                viento REAL,
                riesgo_ia REAL,
                energia_latente REAL
            )
        """)
        conn.execute(
            "INSERT INTO bitacora VALUES (1, 1704067200.0, '2024-01-01', "
            "100.0, 3.0, -2.5, 7.83, 400.0, 2.0, 5000.0)"
        )
        conn.commit()
        conn.close()
        return db_path

    @pytest.fixture
    def titan_db(self, tmp_path):
        db_path = tmp_path / "titan.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE MELATE (
                id INTEGER PRIMARY KEY,
                r1 INT, r2 INT, r3 INT, r4 INT, r5 INT, r6 INT, r7 INT, r8 INT
            )
        """)
        for i in range(50):
            conn.execute(
                "INSERT INTO MELATE VALUES (?, 40, ?, ?, ?, ?, ?, 0, 0)",
                (i, 1 + i % 20, 5 + i % 15, 10 + i % 10, 25 + i % 5, 30 + i % 8),
            )
        conn.execute("""
            CREATE TABLE weights_melate (
                number INTEGER, weight REAL, last_updated TEXT
            )
        """)
        conn.execute(
            "INSERT INTO weights_melate VALUES (7, 9.1e21, '2024-01-01')"
        )
        conn.commit()
        conn.close()
        return db_path

    def test_list_tables(self, cerebro_db):
        loader = LegacyDataLoader(str(cerebro_db))
        tables = loader.list_tables()
        assert "historicos" in tables
        assert "bitacora" in tables

    def test_table_info(self, cerebro_db):
        loader = LegacyDataLoader(str(cerebro_db))
        info = loader.table_info("historicos")
        assert info["row_count"] == 100
        col_names = [c[0] for c in info["columns"]]
        assert "sismo_max_mag" in col_names

    def test_load_historicos(self, cerebro_db):
        loader = LegacyDataLoader(str(cerebro_db))
        df = loader.load_historicos()
        assert len(df) == 100
        assert "sismo_max_mag" in df.columns

    def test_load_historicos_filtered(self, cerebro_db):
        loader = LegacyDataLoader(str(cerebro_db))
        df = loader.load_historicos(start_date="2024-01-10")
        assert len(df) < 100

    def test_load_bitacora(self, cerebro_db):
        loader = LegacyDataLoader(str(cerebro_db))
        df = loader.load_bitacora()
        assert len(df) == 1
        assert "v_fantasma" in df.columns

    def test_historicos_to_snt_input(self, cerebro_db):
        loader = LegacyDataLoader(str(cerebro_db))
        arrays = loader.historicos_to_snt_input()
        assert "kp" in arrays
        assert "sismo_max_mag" in arrays
        assert len(arrays["kp"]) == 100

    def test_load_lottery_game(self, titan_db):
        loader = LegacyDataLoader(str(titan_db))
        df = loader.load_lottery_game("MELATE")
        assert len(df) == 50
        assert "r1" in df.columns

    def test_load_lottery_weights(self, titan_db):
        loader = LegacyDataLoader(str(titan_db))
        df = loader.load_lottery_weights("melate")
        assert len(df) == 1
        assert df.iloc[0]["number"] == 7

    def test_missing_db(self):
        with pytest.raises(FileNotFoundError):
            LegacyDataLoader("/nonexistent/path.db")


# ── Schumann / Tomsk WPC ─────────────────────────────────────────


class TestSchumannConnector:

    @patch("sentinel_omega.infrastructure.api.schumann.get_session")
    def test_fetch_spectrogram(self, mock_get_session):
        from sentinel_omega.infrastructure.api.schumann import fetch_schumann_spectrogram

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        mock_resp.raise_for_status = MagicMock()
        mock_get_session.return_value.get.return_value = mock_resp

        path = fetch_schumann_spectrogram()
        assert path is not None
        import os
        assert os.path.exists(path)
        os.remove(path)

    @patch("sentinel_omega.infrastructure.api.schumann.get_session")
    def test_fetch_spectrogram_failure(self, mock_get_session):
        from sentinel_omega.infrastructure.api.schumann import fetch_schumann_spectrogram

        mock_get_session.return_value.get.side_effect = Exception("Network error")
        path = fetch_schumann_spectrogram()
        assert path is None

    def test_analyze_missing_image(self):
        from sentinel_omega.infrastructure.api.schumann import analyze_spectrogram

        # ingest fix 2026-09-10: missing/unreadable image returns None (no fake 7.83/0.0)
        assert analyze_spectrogram("/nonexistent/image.jpg") is None

    def test_analyze_none_path(self):
        from sentinel_omega.infrastructure.api.schumann import analyze_spectrogram

        assert analyze_spectrogram(None) is None

    @patch("sentinel_omega.infrastructure.api.schumann.fetch_schumann_spectrogram")
    @patch("sentinel_omega.infrastructure.api.schumann.analyze_spectrogram")
    def test_full_pipeline(self, mock_analyze, mock_fetch):
        from sentinel_omega.infrastructure.api.schumann import fetch_schumann_resonance

        mock_fetch.return_value = "/tmp/fake.jpg"
        mock_analyze.return_value = (8.5, 12.0)

        hz, pct = fetch_schumann_resonance(cleanup=False)
        assert hz == 8.5
        assert pct == 12.0

    @patch("sentinel_omega.infrastructure.api.schumann.fetch_schumann_spectrogram")
    def test_full_pipeline_no_download(self, mock_fetch):
        from sentinel_omega.infrastructure.api.schumann import fetch_schumann_resonance

        mock_fetch.return_value = None
        # No download → None (callers use LOCF / skip persist; do not invent baseline)
        assert fetch_schumann_resonance() is None


# ── Geophysical (IERS LOD / Lunar) ───────────────────────────────


class TestGeophysicalConnector:

    @patch("sentinel_omega.infrastructure.api.geophysical.get_session")
    def test_fetch_lod_series(self, mock_get_session):
        from sentinel_omega.infrastructure.api.geophysical import fetch_lod_series

        csv_lines = ["MJD;LOD"]
        for i in range(30):
            mjd = 60310.0 + i
            lod = 0.5 + i * 0.01
            csv_lines.append(f"{mjd};{lod}")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "\n".join(csv_lines)
        mock_resp.raise_for_status = MagicMock()
        mock_get_session.return_value.get.return_value = mock_resp

        df = fetch_lod_series(days=30)
        assert df is not None
        assert "lod_ms" in df.columns
        assert "date" in df.columns
        assert len(df) == 30

    @patch("sentinel_omega.infrastructure.api.geophysical.get_session")
    def test_fetch_lod_failure(self, mock_get_session):
        from sentinel_omega.infrastructure.api.geophysical import fetch_lod_series

        mock_get_session.return_value.get.side_effect = Exception("Network error")
        df = fetch_lod_series()
        assert df is None

    def test_compute_lunar_phase(self):
        from sentinel_omega.infrastructure.api.geophysical import compute_lunar_phase

        result = compute_lunar_phase()
        assert "phase_fraction" in result
        assert "illumination_pct" in result
        assert 0.0 <= result["phase_fraction"] <= 1.0
        assert 0.0 <= result["illumination_pct"] <= 100.0

    def test_compute_lunar_phase_series(self):
        from sentinel_omega.infrastructure.api.geophysical import compute_lunar_phase_series

        phases = compute_lunar_phase_series(days=10)
        assert len(phases) == 10
        assert all(0.0 <= p <= 1.0 for p in phases)


# ── ESA Sentinel / Alfa-2 ─────────────────────────────────────────


class TestESASentinelConnector:

    def test_seismic_zone_bboxes(self):
        from sentinel_omega.infrastructure.api.esa_sentinel import get_seismic_zone_bboxes

        zones = get_seismic_zone_bboxes()
        assert "guerrero_gap" in zones
        assert "oaxaca_costa" in zones
        bbox = zones["guerrero_gap"]
        assert len(bbox) == 4
        assert bbox[0] < bbox[2]
        assert bbox[1] < bbox[3]

    def test_satellite_product_dataclass(self):
        from sentinel_omega.infrastructure.api.esa_sentinel import SatelliteProduct

        p = SatelliteProduct(
            product_id="test-123",
            title="S2B_MSIL2A_20260601",
            platform="S2B",
            datetime_utc="2026-06-01T16:48:49Z",
            cloud_cover=9.4,
            geometry=None,
            download_link=None,
        )
        assert p.platform == "S2B"
        assert p.cloud_cover == 9.4


class TestAlfa2Agent:
    """Alfa-2 canonical behavior: historical baseline inference only (no live learning)."""

    def _ingest_zone(self, agent, zona, *, total_passes, clear_passes, thermal_anomalies=0.0):
        agent.ingest({
            "cobertura_satelital": {
                zona: {
                    "total_passes": total_passes,
                    "clear_passes": clear_passes,
                    "thermal_anomalies": thermal_anomalies,
                }
            }
        })

    def test_analyze_with_coverage(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent

        agent = Alfa2Agent()
        self._ingest_zone(
            agent, "guerrero_gap", total_passes=60, clear_passes=20, thermal_anomalies=0.0
        )
        signal = agent.analyze()
        assert signal.signal_type in SignalType
        assert signal.confidence >= 0.0
        assert signal.data.get("baseline_source") == "historical_precomputed"
        assert signal.data.get("zones_analyzed") == 1

    def test_analyze_with_thermal_alert(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent

        agent = Alfa2Agent()
        # thermal_std in baseline is ~0 → z_thermal blows up with small counts
        self._ingest_zone(
            agent, "guerrero_gap", total_passes=58, clear_passes=20, thermal_anomalies=5.0
        )
        signal = agent.analyze()
        assert signal.signal_type == SignalType.ALERT
        assert signal.confidence > 0.5
        assert signal.data["max_sigma"] >= 3.0

    def test_moderate_anomaly_is_watch(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent

        agent = Alfa2Agent()
        self._ingest_zone(
            agent, "guerrero_gap", total_passes=80, clear_passes=70, thermal_anomalies=0.02
        )
        signal = agent.analyze()
        assert signal.signal_type in (SignalType.WATCH, SignalType.ALERT)
        assert signal.data["max_sigma"] >= 1.0

    def test_analyze_no_data(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent

        agent = Alfa2Agent()
        agent.ingest({})
        signal = agent.analyze()
        assert signal.signal_type == SignalType.NO_SIGNAL

    def test_health_check_uses_baseline(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent

        agent = Alfa2Agent()
        # Canonical: health reflects loaded historical baseline, not ingest presence.
        assert agent.health_check() is True
        agent.ingest({"cobertura_satelital": {"guerrero_gap": {"total_passes": 1, "clear_passes": 0}}})
        assert agent.health_check() is True

    def test_init_has_no_state_path(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent
        import inspect

        sig = inspect.signature(Alfa2Agent.__init__)
        assert "state_path" not in sig.parameters
        agent = Alfa2Agent()
        assert agent._baseline_stats is not None
        assert "guerrero_gap" in agent._baseline_stats or "mexico" in agent._baseline_stats

    def test_near_baseline_is_neutral(self):
        from sentinel_omega.layers.geodynamic.alfa2.agent import Alfa2Agent

        agent = Alfa2Agent()
        # Near historical obs_mean (~58.5) with low thermal → NEUTRAL/low sigma
        self._ingest_zone(
            agent, "guerrero_gap", total_passes=90, clear_passes=30, thermal_anomalies=0.0
        )
        signal = agent.analyze()
        assert signal.signal_type == SignalType.NEUTRAL
        assert signal.data["max_sigma"] < 1.0



# ── OpenWeatherMap ─────────────────────────────────────────────────


class TestOpenWeatherMapConnector:

    def test_monitoring_stations_defined(self):
        from sentinel_omega.infrastructure.api.openweathermap import MONITORING_STATIONS
        assert "tlaxcala" in MONITORING_STATIONS
        assert "oaxaca" in MONITORING_STATIONS
        assert MONITORING_STATIONS["tlaxcala"]["lat"] == 19.31

    def test_atmospheric_reading_dataclass(self):
        from sentinel_omega.infrastructure.api.openweathermap import AtmosphericReading
        r = AtmosphericReading("test", 19.0, -99.0, 1012.0, 22.5, 60.0, 10000, 3.5, 180, 30)
        assert r.station == "test"
        assert r.pressure_hpa == 1012.0
        assert r.temp_c == 22.5

    @patch("sentinel_omega.infrastructure.api.openweathermap.get_session")
    @patch.dict("os.environ", {"OPENWEATHERMAP_KEY": "test_key"})
    def test_fetch_weather(self, mock_get_session):
        from sentinel_omega.infrastructure.api.openweathermap import fetch_weather
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "main": {"pressure": 1005, "temp": 18.5, "humidity": 72},
            "wind": {"speed": 4.2, "deg": 225},
            "clouds": {"all": 50},
            "visibility": 8000,
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get_session.return_value.get.return_value = mock_resp

        reading = fetch_weather(19.31, -98.24, "tlaxcala")
        assert reading is not None
        assert reading.pressure_hpa == 1005
        assert reading.temp_c == 18.5
        assert reading.humidity_pct == 72

    @patch.dict("os.environ", {}, clear=True)
    def test_fetch_weather_no_key(self):
        from sentinel_omega.infrastructure.api.openweathermap import fetch_weather
        reading = fetch_weather(19.31, -98.24)
        assert reading is None

    @patch("sentinel_omega.infrastructure.api.openweathermap.get_session")
    @patch.dict("os.environ", {"OPENWEATHERMAP_KEY": "test_key"})
    def test_fetch_air_quality(self, mock_get_session):
        from sentinel_omega.infrastructure.api.openweathermap import fetch_air_quality
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "list": [{
                "main": {"aqi": 2},
                "components": {"co": 233.5, "so2": 8.1, "no2": 12.0, "pm2_5": 10.0, "pm10": 18.0, "o3": 55.0},
            }],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get_session.return_value.get.return_value = mock_resp

        aq = fetch_air_quality(19.31, -98.24)
        assert aq is not None
        assert aq["co"] == 233.5
        assert aq["so2"] == 8.1
        assert aq["aqi"] == 2

    def test_compute_pressure_gradient(self):
        from sentinel_omega.infrastructure.api.openweathermap import (
            AtmosphericReading,
            compute_pressure_gradient,
        )
        readings = [
            AtmosphericReading("a", 19.0, -99.0, 1005.0, 20.0, 60.0, 10000, 3.0, 180, 30),
            AtmosphericReading("b", 17.0, -97.0, 1015.0, 28.0, 70.0, 10000, 2.0, 200, 20),
            AtmosphericReading("c", 18.0, -98.0, 1010.0, 24.0, 65.0, 10000, 2.5, 190, 25),
        ]
        gradient = compute_pressure_gradient(readings)
        assert gradient["mean_pressure"] == pytest.approx(1010.0)
        assert gradient["pressure_spread"] == pytest.approx(10.0)
        assert "a" in gradient["low_pressure_stations"]
        assert gradient["station_count"] == 3


# ── Telegram ───────────────────────────────────────────────────────


class TestTelegramConnector:

    def test_format_geodynamic_alert(self):
        from sentinel_omega.infrastructure.api.telegram import format_geodynamic_alert
        msg = format_geodynamic_alert("ALERT", 0.85, "Bz dropped to -12 nT")
        assert "SENTINEL OMEGA — GEODYNAMIC" in msg
        assert "85%" in msg
        assert "Bz dropped" in msg

    def test_format_consensus_alert(self):
        from sentinel_omega.infrastructure.api.telegram import format_consensus_alert
        msg = format_consensus_alert("geodynamic", "ALERT", 0.90, 5)
        assert "GEODYNAMIC CONSENSUS" in msg
        assert "90%" in msg

    @patch.dict("os.environ", {}, clear=True)
    def test_send_alert_no_credentials(self):
        from sentinel_omega.infrastructure.api.telegram import send_alert
        result = send_alert("Test message")
        assert result is False

    @patch("sentinel_omega.infrastructure.api.telegram.get_session")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test:token", "TELEGRAM_CHAT_ID": "12345"})
    def test_send_alert_success(self, mock_get_session):
        from sentinel_omega.infrastructure.api.telegram import send_alert
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_get_session.return_value.post.return_value = mock_resp

        result = send_alert("Test alert")
        assert result is True
        mock_get_session.return_value.post.assert_called_once()

    @patch("sentinel_omega.infrastructure.api.telegram.get_session")
    @patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test:token", "TELEGRAM_CHAT_ID": "12345"})
    def test_send_alert_failure(self, mock_get_session):
        from sentinel_omega.infrastructure.api.telegram import send_alert
        mock_get_session.return_value.post.side_effect = Exception("Network error")
        result = send_alert("Test alert")
        assert result is False
