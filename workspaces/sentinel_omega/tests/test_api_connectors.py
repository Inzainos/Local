"""Tests for API connectors (mocked HTTP, no network required)."""

import json
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from sentinel_omega.infrastructure.api.noaa import (
    fetch_kp_index,
    fetch_goes_xray,
    fetch_solar_wind,
    fetch_mag_field,
)
from sentinel_omega.infrastructure.api.crypto import (
    fetch_coingecko_dominance,
    fetch_binance_klines,
    fetch_fear_greed_index,
    fetch_coingecko_market_chart,
)
from sentinel_omega.infrastructure.api.usgs import fetch_earthquakes
from sentinel_omega.infrastructure.api.bolsa import (
    fetch_yahoo_quote,
    fetch_vix,
    fetch_sector_etfs,
)


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = status_code == 200
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ── NOAA ────────────────────────────────────────────────────────────


class TestNOAAConnectors:

    @patch("sentinel_omega.infrastructure.api.noaa.get_session")
    def test_fetch_kp_index(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response([
            {"time_tag": "2024-01-01 00:00:00", "kp_index": "3.00"},
            {"time_tag": "2024-01-01 03:00:00", "kp_index": "4.33"},
        ])
        df = fetch_kp_index()
        assert df is not None
        assert len(df) == 2
        assert "kp_index" in df.columns
        assert "time_tag" in df.columns

    @patch("sentinel_omega.infrastructure.api.noaa.get_session")
    def test_fetch_goes_xray(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response([
            {"time_tag": "2024-01-01T00:00:00Z", "flux": "1.5e-6", "energy": "0.1-0.8nm"},
            {"time_tag": "2024-01-01T00:01:00Z", "flux": "2.0e-6", "energy": "0.1-0.8nm"},
        ])
        df = fetch_goes_xray()
        assert df is not None
        assert "flux" in df.columns

    @patch("sentinel_omega.infrastructure.api.noaa.get_session")
    def test_fetch_solar_wind(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response([
            {"time_tag": "2024-01-01T00:00:00Z", "proton_speed": "400.5", "proton_density": "5.2"},
        ])
        df = fetch_solar_wind()
        assert df is not None

    @patch("sentinel_omega.infrastructure.api.noaa.get_session")
    def test_fetch_mag_field(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response([
            {"time_tag": "2024-01-01T00:00:00Z", "bz_gsm": "-3.5"},
        ])
        df = fetch_mag_field()
        assert df is not None
        assert "bz_gsm" in df.columns

    @patch("sentinel_omega.infrastructure.api.noaa.get_session")
    def test_fetch_kp_network_error(self, mock_get):
        mock_get.return_value.get.side_effect = ConnectionError("Network error")
        assert fetch_kp_index() is None


# ── Crypto ──────────────────────────────────────────────────────────


class TestCryptoConnectors:

    @patch("sentinel_omega.infrastructure.api.crypto.get_session")
    def test_fetch_coingecko_dominance(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response({
            "data": {"market_cap_percentage": {"btc": 54.3, "eth": 17.2}}
        })
        result = fetch_coingecko_dominance()
        assert result is not None
        assert result["btc"] == 54.3

    @patch("sentinel_omega.infrastructure.api.crypto.get_session")
    def test_fetch_binance_klines(self, mock_get):
        kline = [
            1704067200000, "42000.0", "42500.0", "41800.0", "42300.0", "1500.0",
            1704153599999, "63000000.0", 50000, "750.0", "31500000.0", "0",
        ]
        mock_get.return_value.get.return_value = _mock_response([kline])
        df = fetch_binance_klines("BTCUSDT", limit=1)
        assert df is not None
        assert len(df) == 1
        assert "close" in df.columns
        assert df["close"].iloc[0] == pytest.approx(42300.0)

    @patch("sentinel_omega.infrastructure.api.crypto.get_session")
    def test_fetch_fear_greed(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response({
            "data": [{"value": "25", "value_classification": "Extreme Fear", "timestamp": "1704067200"}]
        })
        result = fetch_fear_greed_index()
        assert result is not None
        assert result["value"] == 25
        assert result["classification"] == "Extreme Fear"

    @patch("sentinel_omega.infrastructure.api.crypto.get_session")
    def test_fetch_coingecko_chart(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response({
            "prices": [[1704067200000, 42000.0], [1704153600000, 42500.0]]
        })
        df = fetch_coingecko_market_chart("bitcoin", days=2)
        assert df is not None
        assert len(df) == 2

    @patch("sentinel_omega.infrastructure.api.crypto.get_session")
    def test_fetch_dominance_network_error(self, mock_get):
        mock_get.return_value.get.side_effect = ConnectionError("Network error")
        assert fetch_coingecko_dominance() is None


# ── USGS ────────────────────────────────────────────────────────────


class TestUSGSConnector:

    @patch("sentinel_omega.infrastructure.api.usgs.get_session")
    def test_fetch_earthquakes(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response({
            "features": [
                {
                    "properties": {"time": 1704067200000, "mag": 5.2, "place": "Alaska", "type": "earthquake"},
                    "geometry": {"coordinates": [-150.0, 61.0, 10.0]},
                },
                {
                    "properties": {"time": 1704153600000, "mag": 4.8, "place": "Chile", "type": "earthquake"},
                    "geometry": {"coordinates": [-71.0, -33.0, 30.0]},
                },
            ]
        })
        df = fetch_earthquakes(min_magnitude=4.5, days=7)
        assert df is not None
        assert len(df) == 2
        assert "magnitude" in df.columns
        assert "latitude" in df.columns

    @patch("sentinel_omega.infrastructure.api.usgs.get_session")
    def test_fetch_earthquakes_network_error(self, mock_get):
        mock_get.return_value.get.side_effect = ConnectionError("Network error")
        assert fetch_earthquakes() is None


# ── Bolsa ───────────────────────────────────────────────────────────


class TestBolsaConnectors:

    @patch("sentinel_omega.infrastructure.api.bolsa.get_session")
    def test_fetch_yahoo_quote(self, mock_get):
        mock_get.return_value.get.return_value = _mock_response({
            "chart": {"result": [{
                "timestamp": [1704067200, 1704153600],
                "indicators": {"quote": [{
                    "open": [150.0, 151.0],
                    "high": [152.0, 153.0],
                    "low": [149.0, 150.0],
                    "close": [151.0, 152.0],
                    "volume": [1000000, 1100000],
                }]},
            }]}
        })
        df = fetch_yahoo_quote("AAPL", days=2)
        assert df is not None
        assert len(df) == 2
        assert "close" in df.columns

    @patch("sentinel_omega.infrastructure.api.bolsa.get_session")
    def test_fetch_yahoo_network_error(self, mock_get):
        mock_get.return_value.get.side_effect = ConnectionError("Network error")
        assert fetch_yahoo_quote("AAPL") is None
