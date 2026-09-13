"""Entrenamiento del IsolationForest sobre metrics_history y export a ONNX.
Invocado desde scripts/train_baseline.py, no desde el ciclo de cron normal."""
import numpy as np
from sklearn.ensemble import IsolationForest

from .detector import FEATURES


def train(rows: list[tuple], contamination: float = 0.02) -> IsolationForest:
    """rows: filas de storage.db.load_metrics_history() en el mismo orden
    que FEATURES (ver schema de metrics_history)."""
    X = np.array([[v if v is not None else 0 for v in row] for row in rows], dtype=np.float32)
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(X)
    return model


def export_onnx(model: IsolationForest, out_path: str):
    from skl2onnx import to_onnx
    n_features = int(getattr(model, 'n_features_in_', len(FEATURES)))
    # max_features must match given feature count for skl2onnx IsolationForest
    if getattr(model, 'max_features_', None) is not None and model.max_features_ != n_features:
        model.max_features_ = n_features
    onnx_model = to_onnx(model, X=np.zeros((1, n_features), dtype=np.float32), target_opset={'': 12, 'ai.onnx.ml': 3})
    with open(out_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
