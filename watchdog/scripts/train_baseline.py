#!/usr/bin/env python3
"""Entrena el detector de anomalias con el historial acumulado y exporta a
ONNX. Correr manualmente despues de unos dias de que el cron este activo
(main.py light/heavy alimentan metrics_history en cada corrida).

Uso:
  cd /watchdog && .venv/bin/python scripts/train_baseline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from watchdog import config as cfgmod  # noqa: E402
from watchdog.anomaly import baseline  # noqa: E402
from watchdog.storage import db  # noqa: E402


def main():
    cfg = cfgmod.load_config()
    cfgmod.ensure_dirs(cfg)

    with db.connect(cfg) as conn:
        rows = db.load_metrics_history(conn)

    min_samples = cfg.get("anomaly", "min_baseline_samples", default=200)
    if len(rows) < min_samples:
        print(f"Todavia no hay suficiente historial: {len(rows)}/{min_samples} muestras. "
              f"Dejar el cron corriendo unos dias mas.")
        return 1

    contamination = cfg.get("anomaly", "contamination", default=0.02)
    model = baseline.train(rows, contamination=contamination)

    out_path = cfg.get("paths", "model_path")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    baseline.export_onnx(model, out_path)
    print(f"Modelo entrenado con {len(rows)} muestras -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
