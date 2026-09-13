"""Detector de anomalias de comportamiento del EQUIPO (no de 'atacantes en
general' - eso no es realista). Un IsolationForest entrenado sobre la serie
historica de metricas de ESTE sistema (num procesos, conexiones, CPU, etc.),
exportado a ONNX y evaluado en cada corrida liviana.

Sin suficiente historial (min_baseline_samples en config.yaml) simplemente
no hay modelo todavia: el scanner sigue funcionando en modo heuristico puro
via los otros modulos. Correr scripts/train_baseline.py una vez que haya
unos dias de datos acumulados (main.py light/heavy ya alimentan la tabla
metrics_history en cada corrida)."""
from pathlib import Path

import numpy as np

FEATURES = [
    "num_processes", "num_listening_ports", "num_connections",
    "num_unique_parents", "cpu_percent", "mem_percent", "num_unpackaged_exec_paths",
]


def metrics_to_vector(metrics: dict) -> np.ndarray:
    return np.array([[metrics.get(f, 0) or 0 for f in FEATURES]], dtype=np.float32)


def load_model(model_path: str):
    path = Path(model_path)
    if not path.exists():
        return None
    try:
        import onnxruntime as ort
        return ort.InferenceSession(str(path))
    except Exception:
        return None


def score(session, metrics: dict) -> float | None:
    """Devuelve el anomaly score de IsolationForest (mas negativo = mas
    anomalo). None si no hay modelo entrenado todavia."""
    if session is None:
        return None
    vec = metrics_to_vector(metrics)
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: vec})
    # skl2onnx expone [label, scores] para IsolationForest; el segundo
    # output trae el decision_function score.
    for out in outputs:
        arr = np.asarray(out)
        if arr.dtype.kind == "f":
            return float(arr.reshape(-1)[0])
    return None
