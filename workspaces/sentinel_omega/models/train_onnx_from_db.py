#!/usr/bin/env python3
"""
Reentrenamiento ONNX desde firmas reales (TBL_FIRMAS) + histórico.

Prioridad de datos:
  1. Features de TBL_FIRMAS (features_json) mapeadas al vector ONNX del bot
  2. Si hay pocas muestras (< MIN_SAMPLES), mezcla con bootstrap físico
  3. Si la DB está vacía, solo bootstrap (equivalente a train_onnx_bootstrap)

Exporta a sentinel_omega/models/*.onnx — listo para los agentes.

Uso:
  python -m sentinel_omega.models.train_onnx_from_db --db-path data/SENTINEL_OMEGA_PRO.db
  python sentinel_omega/models/train_onnx_from_db.py --db-path ... --min-samples 50
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ONNX_RETRAIN] %(levelname)s %(message)s",
)
logger = logging.getLogger("onnx_retrain")

MODELS_DIR = Path(__file__).resolve().parent
MIN_SAMPLES = 80
RANDOM_SEED = 42

BOT_DIMS = {
    "alfa1": 10,
    "alfa2": 8,
    "beta1": 16,
    "beta2": 16,
    "delta": 16,
    "omega": 12,
}

FEATURE_ORDER: Dict[str, List[str]] = {
    "alfa1": [
        "bz_mean", "viento_avg", "proton_max", "proton_max",
        "bz_min", "kp_mean", "kp_max", "bz_deriv_std",
        "viento_max", "bz_mean_72h",
    ],
    "alfa2": [
        "satellite_coverage_score", "satellite_thermal_anomalies",
        "satellite_clear_passes", "satellite_coverage_score",
        "satellite_clear_passes", "satellite_thermal_anomalies",
        "satellite_coverage_score", "satellite_thermal_anomalies",
    ],
    "beta1": [
        "kp_mean", "kp_max", "schumann_mean", "schumann_std",
        "sismo_count_win", "sismo_max_mag_win", "fase_lunar",
        "es_sicigia", "kp_max_72h", "sismo_count_72h",
        "schumann_mean", "schumann_std", "kp_mean", "kp_max",
        "fase_lunar", "sismo_max_mag_win",
    ],
    "beta2": [
        "so2_kt_win", "erupciones_win", "so2_kt_90d", "erupciones_90d",
        "so2_kt_win", "erupciones_win", "so2_kt_90d", "erupciones_90d",
        "so2_kt_win", "erupciones_win", "so2_kt_90d", "erupciones_90d",
        "so2_kt_win", "erupciones_win", "so2_kt_90d", "erupciones_90d",
    ],
    "delta": [
        "btc_volatilidad", "btc_vol_max", "btc_ret_win", "btc_vol_72h",
        "btc_volatilidad", "btc_ret_win", "btc_vol_max",
        "btc_volatilidad", "btc_vol_max", "btc_ret_win", "btc_vol_72h",
        "btc_volatilidad", "btc_ret_win", "btc_vol_max",
        "btc_vol_72h", "btc_ret_win",
    ],
    "omega": [
        "fase_lunar", "es_sicigia", "schumann_mean", "schumann_std",
        "bz_mean", "kp_mean", "viento_avg", "bz_min",
        "kp_max", "schumann_mean", "fase_lunar", "kp_max_72h",
    ],
}

NO_SIGNAL, NEUTRAL, WATCH, ALERT, BULLISH, BEARISH = 0, 1, 2, 3, 4, 5

EVENT_CLASS_LABEL = {
    "SISMO_M7": (ALERT, 0.90),
    "SISMO_M6": (ALERT, 0.80),
    "SISMO_M5": (WATCH, 0.65),
    "SISMO_M4": (WATCH, 0.50),
    "ERUPCION_VEI5": (ALERT, 0.85),
    "ERUPCION_VEI4": (ALERT, 0.75),
    "ERUPCION_VEI3": (WATCH, 0.55),
    "TORMENTA_Kp9": (ALERT, 0.90),
    "TORMENTA_Kp7": (ALERT, 0.80),
    "TORMENTA_Kp6": (WATCH, 0.60),
    "TSUNAMI_M7": (ALERT, 0.90),
    "TSUNAMI_M6": (ALERT, 0.75),
    "VOLCAN": (WATCH, 0.55),
    "DEFAULT": (NEUTRAL, 0.30),
}

ESTADO_BOOST = {
    "consolidada": 0.10,
    "recurrente": 0.05,
    "observada": 0.02,
    "nueva": 0.0,
}


def _label_from_row(event_class: str, estado: str) -> Tuple[float, float]:
    sig, conf = EVENT_CLASS_LABEL.get(event_class, EVENT_CLASS_LABEL["DEFAULT"])
    conf = min(0.95, conf + ESTADO_BOOST.get(estado, 0.0))
    return float(conf), float(sig)


def _features_to_vector(features: dict, bot: str) -> np.ndarray:
    order = FEATURE_ORDER[bot]
    dim = BOT_DIMS[bot]
    vec = np.zeros(dim, dtype=np.float32)
    for i, key in enumerate(order[:dim]):
        val = features.get(key)
        if val is None:
            continue
        try:
            fv = float(val)
            if np.isfinite(fv):
                vec[i] = fv
        except (TypeError, ValueError):
            pass
    return vec


def load_firmas_from_db(db_path: str) -> Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """bot -> (X, y_conf, y_sig)"""
    out: Dict[str, list] = {b: [] for b in BOT_DIMS}
    path = Path(db_path)
    if not path.exists():
        logger.warning(f"DB no existe: {db_path}")
        return {}

    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT bot_name, event_class, estado, features_json FROM TBL_FIRMAS"
        ).fetchall()
    except sqlite3.Error as e:
        logger.warning(f"No se pudo leer TBL_FIRMAS: {e}")
        conn.close()
        return {}
    conn.close()

    logger.info(f"Firmas en DB: {len(rows)}")
    for bot_name, event_class, estado, features_json in rows:
        bot = (bot_name or "").lower()
        if bot not in BOT_DIMS:
            continue
        try:
            features = json.loads(features_json) if features_json else {}
        except json.JSONDecodeError:
            continue
        if not isinstance(features, dict) or not features:
            continue
        vec = _features_to_vector(features, bot)
        if not np.any(np.abs(vec) > 1e-12):
            continue
        conf, sig = _label_from_row(event_class or "DEFAULT", estado or "nueva")
        out[bot].append((vec, conf, sig))

    result = {}
    for bot, samples in out.items():
        if not samples:
            continue
        X = np.stack([s[0] for s in samples]).astype(np.float32)
        y_conf = np.array([s[1] for s in samples], dtype=np.float32)
        y_sig = np.array([s[2] for s in samples], dtype=np.float32)
        result[bot] = (X, y_conf, y_sig)
        logger.info(f"  {bot}: {len(samples)} firmas reales")
    return result


def load_juez_feedback(db_path: str) -> Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Etiquetas desde TBL_JUEZ_AUDITORIA (ACIERTO/FALLO/FALSO_POSITIVO)."""
    out: Dict[str, list] = {b: [] for b in BOT_DIMS}
    path = Path(db_path)
    if not path.exists():
        return {}
    conn = sqlite3.connect(str(path))
    try:
        rows = conn.execute(
            "SELECT bot_name, prediccion, confianza, resultado, detalles_json "
            "FROM TBL_JUEZ_AUDITORIA "
            "WHERE resultado IN ('ACIERTO','FALLO','FALSO_POSITIVO') "
            "AND fase = 'viva'"
        ).fetchall()
    except sqlite3.Error as e:
        logger.info(f"Juez sin filas útiles: {e}")
        conn.close()
        return {}
    conn.close()
    logger.info(f"Juez feedback vivo: {len(rows)} filas")
    for bot_name, prediccion, confianza, resultado, det_json in rows:
        bot = (bot_name or "").lower()
        if bot in ("padre", "padre_geo"):
            bot = "omega"
        if bot not in BOT_DIMS:
            continue
        features = {}
        try:
            det = json.loads(det_json) if det_json else {}
            if isinstance(det, dict):
                features = {k: v for k, v in det.items() if isinstance(v, (int, float))}
                for m in (det.get("firma_matches") or [])[:1]:
                    if isinstance(m, dict):
                        features.update({k: v for k, v in m.items() if isinstance(v, (int, float))})
        except json.JSONDecodeError:
            pass
        vec = _features_to_vector(features, bot)
        pred = (prediccion or "").lower()
        conf0 = float(confianza or 0.3)
        if resultado == "ACIERTO":
            if pred in ("alert", "watch"):
                sig, conf = (ALERT if pred == "alert" else WATCH), min(0.95, conf0 + 0.05)
            else:
                sig, conf = NEUTRAL, 0.35
        elif resultado == "FALSO_POSITIVO":
            sig, conf = NEUTRAL, 0.2
        else:
            sig, conf = ALERT, 0.7
        if not np.any(np.abs(vec) > 1e-12):
            vec = np.zeros(BOT_DIMS[bot], dtype=np.float32)
            vec[0] = conf
        out[bot].append((vec, conf, float(sig)))
    result = {}
    for bot, samples in out.items():
        if not samples:
            continue
        X = np.stack([s[0] for s in samples]).astype(np.float32)
        y_conf = np.array([s[1] for s in samples], dtype=np.float32)
        y_sig = np.array([s[2] for s in samples], dtype=np.float32)
        result[bot] = (X, y_conf, y_sig)
        logger.info(f"  juez/{bot}: {len(samples)} muestras")
    return result


def _merge_xy(a, b):
    if not a:
        return b
    if not b:
        return a
    X = np.vstack([a[0], b[0]]).astype(np.float32)
    yc = np.concatenate([a[1], b[1]]).astype(np.float32)
    ys = np.concatenate([a[2], b[2]]).astype(np.float32)
    return X, yc, ys


def bootstrap_xy(bot: str, n: int = 2500) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    sys.path.insert(0, str(MODELS_DIR.parent.parent))
    from sentinel_omega.models.train_onnx_bootstrap import (
        gen_alfa1, gen_alfa2, gen_beta1, gen_beta2, gen_delta, gen_omega,
    )
    gens = {
        "alfa1": gen_alfa1, "alfa2": gen_alfa2, "beta1": gen_beta1,
        "beta2": gen_beta2, "delta": gen_delta, "omega": gen_omega,
    }
    X, y_conf, y_sig = gens[bot](n)
    return X.astype(np.float32), y_conf.astype(np.float32), y_sig.astype(np.float32)


def merge_or_bootstrap(
    bot: str,
    firmas: Dict[str, Tuple[np.ndarray, np.ndarray, np.ndarray]],
    min_samples: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, str]:
    if bot in firmas and len(firmas[bot][0]) >= min_samples:
        X, yc, ys = firmas[bot]
        return X, yc, ys, f"db-only ({len(X)})"
    Xb, ycb, ysb = bootstrap_xy(bot)
    if bot not in firmas or len(firmas[bot][0]) == 0:
        return Xb, ycb, ysb, f"bootstrap-only ({len(Xb)})"
    Xf, ycf, ysf = firmas[bot]
    target_real = max(len(Xf), min(len(Xb) // 2, max(min_samples, len(Xf) * 8)))
    idx = np.random.default_rng(RANDOM_SEED).choice(len(Xf), size=target_real, replace=True)
    X = np.vstack([Xf[idx], Xb]).astype(np.float32)
    yc = np.concatenate([ycf[idx], ycb]).astype(np.float32)
    ys = np.concatenate([ysf[idx], ysb]).astype(np.float32)
    return X, yc, ys, f"hybrid real={len(Xf)}+boot={len(Xb)} → {len(X)}"


def train_export(bot: str, X: np.ndarray, y_conf: np.ndarray, y_sig: np.ndarray) -> Path:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.multioutput import MultiOutputRegressor
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    y = np.column_stack([y_conf, y_sig])
    model = MultiOutputRegressor(
        RandomForestRegressor(
            n_estimators=80, max_depth=10, min_samples_leaf=3,
            random_state=RANDOM_SEED, n_jobs=-1,
        )
    )
    model.fit(X, y)
    pred = model.predict(X)
    mae = float(np.mean(np.abs(pred[:, 0] - y_conf)))
    logger.info(f"  {bot}: train MAE conf={mae:.4f}  n={len(X)}")

    onnx_model = convert_sklearn(
        model,
        initial_types=[("input", FloatTensorType([None, X.shape[1]]))],
        target_opset=12,
    )
    names = {
        "alfa1": "alfa1_spaceweather_rf.onnx",
        "alfa2": "alfa2_satellite_cnn.onnx",
        "beta1": "beta1_schumann_fft.onnx",
        "beta2": "beta2_atmospheric_cnn.onnx",
        "delta": "delta_financial_lstm.onnx",
        "omega": "omega_espacial_rf.onnx",
    }
    out = MODELS_DIR / names[bot]
    with open(out, "wb") as f:
        f.write(onnx_model.SerializeToString())
    logger.info(f"  wrote {out.name} ({out.stat().st_size} bytes)")
    return out


def retrain(db_path: str, min_samples: int = MIN_SAMPLES, bots: Optional[List[str]] = None) -> dict:
    bots = bots or list(BOT_DIMS.keys())
    firmas = load_firmas_from_db(db_path)
    juez = load_juez_feedback(db_path)
    for bot, xy in juez.items():
        firmas[bot] = _merge_xy(firmas.get(bot), xy)
        logger.info(f"  merge juez→{bot}: n={len(firmas[bot][0])}")
    results = {}
    for bot in bots:
        X, yc, ys, source = merge_or_bootstrap(bot, firmas, min_samples)
        logger.info(f"=== {bot}: {source} ===")
        path = train_export(bot, X, yc, ys)
        results[bot] = {"path": str(path), "n": int(len(X)), "source": source}
    meta = {
        "retrained_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "db_path": str(db_path),
        "bots": results,
    }
    (MODELS_DIR / "models_meta.json").write_text(json.dumps(meta, indent=2))
    return results


def main():
    ap = argparse.ArgumentParser(description="Reentrenar modelos ONNX desde firmas/DB")
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    ap.add_argument("--bots", nargs="*", default=None)
    args = ap.parse_args()
    res = retrain(args.db_path, min_samples=args.min_samples, bots=args.bots)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
