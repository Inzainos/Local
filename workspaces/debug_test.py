import pytest
from unittest.mock import patch
import numpy as np
import pandas as pd

def _mock_kp_df():
    return pd.DataFrame({
        "time_tag": pd.date_range("2024-01-01", periods=100, freq="3h"),
        "kp_index": np.random.uniform(0, 5, 100),
    })

def _mock_eq_df():
    return pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=50, freq="1D"),
        "mag": np.random.uniform(2.5, 7.0, 50),
    })

@patch("sentinel_omega.infrastructure.pipeline.data_pipeline.compute_lunar_phase_series")
@patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_lod_series")
@patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_schumann_resonance")
@patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_earthquakes")
@patch("sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_kp_index")
def test_beta1_data(mock_kp, mock_eq, mock_schumann, mock_lod, mock_lunar):
    mock_kp.return_value = _mock_kp_df()
    mock_eq.return_value = _mock_eq_df()
    mock_schumann.return_value = (8.12, 3.5)
    mock_lod.return_value = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=90, freq="1D"),
        "lod_ms": np.random.uniform(-0.5, 1.5, 90),
    })
    mock_lunar.return_value = np.linspace(0, 1, 30)

    from sentinel_omega.infrastructure.pipeline.data_pipeline import GeodynamicPipeline
    print("Creating pipeline...")
    pipe = GeodynamicPipeline()
    print("Fetching data...")
    data = pipe.fetch_beta1_data()
    print("Done fetching")
    assert "kp_series" in data
    assert len(data["kp_series"]) == 100
    assert "seismic_magnitudes" in data
    assert data["schumann_frequency"] == 8.12
    assert data["schumann_activity"] == 3.5
    assert "lod_ms" in data
    assert len(data["lod_ms"]) == 90
    assert "lunar_phase" in data
    assert len(data["lunar_phase"]) == 30
    print("All assertions passed!")

test_beta1_data()
