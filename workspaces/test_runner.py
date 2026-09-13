from sentinel_omega.infrastructure.pipeline.layer_runners import GeodynamicLayerRunner
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

def _mock_mag_df():
    return pd.DataFrame({
        'time_tag': pd.date_range('2024-01-01', periods=100, freq='1min'),
        'bt': np.random.uniform(-20, 20, 100),
        'bz': np.random.uniform(-20, 20, 100),
    })

def _mock_wind_df():
    return pd.DataFrame({
        'time_tag': pd.date_range('2024-01-01', periods=100, freq='1min'),
        'proton_speed': np.random.uniform(300, 600, 100),
        'proton_density': np.random.uniform(2, 10, 100),
    })

def _mock_kp_df():
    return pd.DataFrame({
        'time_tag': pd.date_range('2024-01-01', periods=100, freq='3h'),
        'kp': np.random.uniform(0, 9, 100),
    })

def _mock_eq_df():
    return pd.DataFrame({
        'time': pd.date_range('2024-01-01', periods=20, freq='1D'),
        'magnitude': np.random.uniform(4.0, 7.0, 20),
        'place': [f'City {i}, Region {i % 5}' for i in range(20)],
        'depth_km': np.random.uniform(5, 100, 20),
        'longitude': np.random.uniform(-180, 180, 20),
        'latitude': np.random.uniform(-90, 90, 20),
        'type': ['earthquake'] * 20,
    })

def _mock_binance_df():
    return pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=90, freq='1D'),
        'open': np.random.uniform(40000, 50000, 90),
        'high': np.random.uniform(40000, 50000, 90),
        'low': np.random.uniform(40000, 50000, 90),
        'close': np.random.uniform(40000, 50000, 90),
        'volume': np.random.uniform(1000, 5000, 90),
    })

with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_mag_field', return_value=_mock_mag_df()):
    with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_solar_wind', return_value=_mock_wind_df()):
        with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_kp_index', return_value=_mock_kp_df()):
            with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_earthquakes', return_value=_mock_eq_df()):
                with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_fear_greed_index', return_value={'value': 50, 'classification': 'Neutral'}):
                    with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_schumann_resonance', return_value=(7.95, 1.2)):
                        with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_lod_series', return_value=pd.DataFrame({
                            'date': pd.date_range('2024-01-01', periods=30, freq='1D'),
                            'lod_ms': np.random.uniform(0.0, 1.0, 30),
                        })):
                            with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.compute_lunar_phase_series', return_value=np.linspace(0, 1, 30)):
                                with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_goes_xray', return_value=pd.DataFrame({
                                    'time_tag': pd.date_range('2024-01-01', periods=100, freq='1min'),
                                    'flux': np.random.uniform(1e-7, 1e-4, 100),
                                })):
                                    with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_neo_hazard_summary', return_value={'hazardous_count': 5, 'closest_hazardous_ld': 12.3}):
                                        with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_electron_flux', return_value=pd.DataFrame({'time_tag': pd.date_range('2024-01-01', periods=71, freq='5min'), 'flux': np.random.uniform(100, 10000, 71)})):
                                            with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_monitoring_network', return_value=[]):
                                                with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_air_quality', return_value=None):
                                                    with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_coingecko_dominance', return_value={'btc': 54.0}):
                                                        with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_binance_klines', return_value=_mock_binance_df()):
                                                            with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_yield_spread', return_value=0.8):
                                                                with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_vix', return_value=pd.DataFrame({'close': [18.0], 'volume': [1e6]})):
                                                                    with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.fetch_sector_etfs', return_value={
                                                                        'XLK': pd.DataFrame({'close': [200.0], 'volume': [5e6]}),
                                                                    }):
                                                                        with patch('sentinel_omega.infrastructure.pipeline.data_pipeline.GeodynamicPipeline.fetch_jupiter_data', return_value={}):
                                                                            runner = GeodynamicLayerRunner(enable_satellite=False)
                                                                            consensus = runner.run()
                                                                            print('Consensus:', consensus)
                                                                            print('Signal:', consensus.final_signal if consensus else None)
