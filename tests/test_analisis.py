"""
Tests para analisis_comportamiento.py
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from analisis_comportamiento import (
    analisis_edad,
    analisis_genero,
    analisis_geografico,
    analisis_mesas,
    analisis_participacion_general,
    analisis_cohorte_afiliacion,
    analisis_cimatica,
    analisis_red_afiliados,
    analisis_outliers,
    generar_reporte_completo,
    get_resumen_ejecutivo,
    load_afiliados,
    load_participacion,
    get_db_connection,
)


# Fixtures
@pytest.fixture
def df_afiliados_sample():
    """DataFrame de ejemplo con afiliados sintéticos."""
    np.random.seed(42)
    n = 1000
    data = {
        "id": range(1, n + 1),
        "dni": [f"{np.random.randint(10000000, 99999999)}" for _ in range(n)],
        "nombre": [f"Nombre{i}" for i in range(n)],
        "apellido": [f"Apellido{i}" for i in range(n)],
        "fecha_nacimiento": pd.date_range("1930-01-01", periods=n, freq="D"),
        "fecha_afiliacion": pd.date_range("2020-01-01", periods=n, freq="D"),
        "genero": np.random.choice(["M", "F"], n),
        "estado": np.random.choice(["activo", "inactivo", "suspendido"], n, p=[0.85, 0.1, 0.05]),
        "provincia": np.random.choice(
            ["Buenos Aires", "CABA", "Córdoba", "Santa Fe", "Mendoza"], n
        ),
        "localidad": np.random.choice(
            ["Centro", "Norte", "Sur", "Este", "Oeste"], n
        ),
        "mesa_votacion": np.random.randint(1, 100, n),
        "email": [f"user{i}@test.com" for i in range(n)],
        "telefono": [f"11{np.random.randint(10000000, 99999999)}" for _ in range(n)],
    }
    df = pd.DataFrame(data)
    return df


@pytest.fixture
def df_eventos_sample():
    """DataFrame de eventos electorales sintéticos."""
    np.random.seed(42)
    n = 10
    data = {
        "id": range(1, n + 1),
        "nombre": [f"Elección {i}" for i in range(n)],
        "fecha": pd.date_range("2022-01-01", periods=n, freq="6M"),
        "activo": [1] * n,
    }
    return pd.DataFrame(data)


@pytest.fixture
def df_participacion_sample(df_afiliados_sample, df_eventos_sample):
    """DataFrame de participación sintético."""
    np.random.seed(42)
    n_participaciones = 500
    data = {
        "id": range(1, n_participaciones + 1),
        "afiliado_id": np.random.choice(df_afiliados_sample["id"], n_participaciones),
        "evento_id": np.random.choice(df_eventos_sample["id"], n_participaciones),
        "voto_emitido": np.random.choice([0, 1], n_participaciones, p=[0.3, 0.7]),
    }
    return pd.DataFrame(data)


class TestGenerarReporteCompleto:
    """Test de integracion para reporte completo."""

    def test_generar_reporte_completo(self, df_afiliados_sample):
        import analisis_comportamiento as ac
        original_load = ac.load_afiliados
        ac.load_afiliados = lambda filters=None: df_afiliados_sample
        
        original_load_part = ac.load_participacion
        ac.load_participacion = lambda evento_id=None: pd.DataFrame()
        
        original_conn = ac.get_db_connection
        def mock_conn():
            class MockConn:
                def execute(self, q):
                    class MockCursor:
                        def fetchall(self):
                            return [{"id": 1, "nombre": "Test Event"}]
                    return MockCursor()
                def close(self):
                    pass
            return MockConn()
        ac.get_db_connection = mock_conn
        
        try:
            reporte = generar_reporte_completo()
            assert "fecha_generacion" in reporte
            assert "filtros_aplicados" in reporte
            assert "total_afiliados_analizados" in reporte
            assert "demografico" in reporte
            assert "temporal" in reporte
            assert "redes" in reporte
            assert "outliers" in reporte
            assert "participacion" in reporte
        finally:
            ac.load_afiliados = original_load
            ac.load_participacion = original_load_part
            ac.get_db_connection = original_conn


class TestGetResumenEjecutivo:
    """Test para resumen ejecutivo."""

    def test_get_resumen_ejecutivo(self, df_afiliados_sample):
        import analisis_comportamiento as ac
        original_load = ac.load_afiliados
        ac.load_afiliados = lambda filters=None: df_afiliados_sample
        
        try:
            resumen = get_resumen_ejecutivo()
            assert "total" in resumen
            assert "activos" in resumen
            assert "provincias_unicas" in resumen
            assert resumen["total"] == 1000
        finally:
            ac.load_afiliados = original_load


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
