"""Data pipeline — wires real APIs into agent ingest() methods."""

from sentinel_omega.infrastructure.pipeline.data_pipeline import GeodynamicPipeline
from sentinel_omega.infrastructure.pipeline.layer_runners import GeodynamicLayerRunner
from sentinel_omega.infrastructure.pipeline.backcast import run_backcast
from sentinel_omega.infrastructure.pipeline.legacy_loader import LegacyDataLoader
from sentinel_omega.infrastructure.pipeline.reporte_sentinel import (
    reporte_general,
    reporte_padre,
    reporte_omega,
)
from sentinel_omega.infrastructure.pipeline.mantenimiento import (
    barrido_diario,
    construir_correlaciones_padre,
    evaluar_sesgo_aprendizaje,
    construir_correlaciones_omega,
)

# Persistent LOCF (memory + tbl_locf_cache)
try:
    from sentinel_omega.infrastructure.pipeline import data_pipeline_locf_patch  # noqa: F401
except Exception:
    pass

# Juez: padre + per-bot predictions
try:
    from sentinel_omega.infrastructure.pipeline.juez_cycle_register import (  # noqa: F401
        register_cycle_predictions,
    )
except Exception:
    pass
