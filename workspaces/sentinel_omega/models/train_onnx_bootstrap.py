import json
from pathlib import Path
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.model_selection import train_test_split
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
import onnxruntime as rt

MODELS_DIR = Path(__file__).resolve().parent
MODELS_DIR.mkdir(parents=True, exist_ok=True)
NEUTRAL, WATCH, ALERT, BULLISH, BEARISH = 1, 2, 3, 4, 5
RNG = np.random.default_rng(42)

def export_onnx(model, n_features, path, name):
    initial_type = [("float_input", FloatTensorType([None, n_features]))]
    onx = convert_sklearn(model, initial_types=initial_type, target_opset={"": 17, "ai.onnx.ml": 3})
    path.write_bytes(onx.SerializeToString())
    sess = rt.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    x = np.zeros((1, n_features), dtype=np.float32)
    out = sess.run(None, {sess.get_inputs()[0].name: x})
    print(f"  OK {name}: {path.name} shapes={[o.shape for o in out]}")
    return path

def train_multioutput(X, y_conf, y_sig, n_features, path, name, n_est=40):
    Y = np.column_stack([y_conf, y_sig.astype(float)])
    Xtr, Xte, Ytr, Yte = train_test_split(X, Y, test_size=0.2, random_state=42)
    model = MultiOutputRegressor(RandomForestRegressor(n_estimators=n_est, max_depth=8, random_state=42, n_jobs=2, min_samples_leaf=3))
    model.fit(Xtr, Ytr)
    pred = model.predict(Xte)
    conf_mae = float(np.mean(np.abs(pred[:, 0] - Yte[:, 0])))
    sig_acc = float(np.mean(np.round(pred[:, 1]) == np.round(Yte[:, 1])))
    print(f"  {name}: conf_MAE={conf_mae:.3f} signal_acc={sig_acc:.3f} n={len(X)}")
    export_onnx(model, n_features, path, name)
    return {"conf_mae": conf_mae, "signal_acc": sig_acc, "n_samples": int(len(X)), "n_features": n_features, "file": path.name}

def gen_alfa1(n=4000):
    bz = RNG.normal(-2, 6, n); wind = RNG.normal(420, 80, n).clip(250, 900)
    dens = RNG.normal(6, 3, n).clip(0.1, 40); pflux = RNG.exponential(2, n)
    dst = RNG.normal(-20, 40, n); ae = RNG.exponential(100, n)
    kp = RNG.uniform(0, 9, n); ap = kp * 5 + RNG.normal(0, 3, n)
    bmag = RNG.normal(5, 2, n).clip(1, 30); flow_p = dens * (wind / 100.0) ** 2 * 0.5
    X = np.column_stack([bz, wind, dens, pflux, dst, ae, kp, ap, bmag, flow_p]).astype(np.float32)
    y_sig = np.full(n, NEUTRAL, dtype=float); y_conf = np.full(n, 0.3)
    severe = bz < -10; mod = (bz < -5) & ~severe; storm = kp >= 5
    y_sig[mod] = ALERT; y_conf[mod] = 0.5 + np.clip((-bz[mod] - 5) / 20, 0, 0.3)
    y_sig[severe] = ALERT; y_conf[severe] = 0.75 + np.clip((-bz[severe] - 10) / 40, 0, 0.2)
    y_sig[storm & ~severe] = WATCH; y_conf[storm & ~severe] = np.maximum(y_conf[storm & ~severe], 0.55)
    return X, y_conf, y_sig

def gen_beta1(n=4000):
    energy = RNG.exponential(2, n); hf = RNG.uniform(0, 1, n); period = RNG.uniform(3, 72, n)
    kp_mean = RNG.uniform(0, 7, n); kp_max = np.clip(kp_mean + RNG.uniform(0, 3, n), 0, 9)
    sch_hz = RNG.normal(7.83, 0.3, n); sch_pct = RNG.uniform(0, 50, n)
    lod = RNG.normal(0, 0.5, n); lunar = RNG.uniform(0, 1, n); electron = RNG.exponential(1, n)
    pads = RNG.normal(0, 1, (n, 6))
    X = np.column_stack([energy, hf, period, kp_mean, kp_max, sch_hz, sch_pct, lod, lunar, electron, pads]).astype(np.float32)
    y_sig = np.full(n, NEUTRAL, dtype=float); y_conf = np.full(n, 0.25)
    watch = (sch_pct > 30) & (kp_max < 3); alert = (sch_pct > 40) & (kp_max >= 5)
    y_sig[watch] = WATCH; y_conf[watch] = 0.55 + np.clip((sch_pct[watch] - 30) / 40, 0, 0.3)
    y_sig[alert] = ALERT; y_conf[alert] = 0.7 + np.clip((sch_pct[alert] - 40) / 40, 0, 0.25)
    return X, y_conf, y_sig

def gen_beta2(n=3000):
    pressure = RNG.normal(1013, 8, n); temp = RNG.normal(20, 10, n); humidity = RNG.uniform(20, 100, n)
    visibility = RNG.uniform(100, 20000, n); so2 = RNG.exponential(0.5, n); aqi = RNG.uniform(0, 200, n)
    gradient = RNG.normal(0, 2, n); weather_id = RNG.integers(800, 900, n).astype(float)
    pads = RNG.normal(0, 1, (n, 8))
    X = np.column_stack([pressure, temp, humidity, visibility, so2, aqi, gradient, weather_id, pads]).astype(np.float32)
    y_sig = np.full(n, NEUTRAL, dtype=float); y_conf = np.full(n, 0.25)
    elev = (pressure < 1005) | (so2 > 2.0); y_sig[elev] = WATCH; y_conf[elev] = 0.5
    strong = (pressure < 1000) & (so2 > 3.0); y_sig[strong] = ALERT; y_conf[strong] = 0.75
    return X, y_conf, y_sig

def gen_delta(n=3000):
    fgi = RNG.uniform(0, 100, n); vix = RNG.uniform(10, 50, n); btc_dom = RNG.uniform(0.3, 0.7, n)
    btc_vol = RNG.exponential(2, n); btc_ret = RNG.normal(0, 5, n); yield_sp = RNG.normal(1, 1, n)
    cross = RNG.uniform(0, 1, n); pads = RNG.normal(0, 1, (n, 9))
    X = np.column_stack([fgi, vix, btc_dom, btc_vol, btc_ret, yield_sp, cross, pads]).astype(np.float32)
    y_sig = np.full(n, NEUTRAL, dtype=float); y_conf = np.full(n, 0.3)
    bear = (fgi < 25) | (vix > 30); bull = (fgi > 75) & (vix < 18)
    y_sig[bear] = BEARISH; y_conf[bear] = 0.6
    y_sig[bull] = BULLISH; y_conf[bull] = 0.6
    watch = (fgi < 20) & (vix > 35); y_sig[watch] = WATCH; y_conf[watch] = 0.75
    return X, y_conf, y_sig

def gen_alfa2(n=2500):
    coverage = RNG.uniform(0, 1, n); thermal = RNG.poisson(1, n).astype(float)
    clear = RNG.poisson(5, n).astype(float); total = clear + RNG.poisson(3, n).astype(float)
    revisit = RNG.uniform(1, 14, n); cloud = 1.0 - coverage
    anomaly_rate = thermal / np.maximum(total, 1); pad = RNG.normal(0, 0.1, n)
    X = np.column_stack([coverage, thermal, clear, total, revisit, cloud, anomaly_rate, pad]).astype(np.float32)
    y_sig = np.full(n, NEUTRAL, dtype=float); y_conf = np.full(n, 0.25)
    watch = thermal >= 2; y_sig[watch] = WATCH; y_conf[watch] = 0.55
    alert = thermal >= 5; y_sig[alert] = ALERT; y_conf[alert] = 0.8
    return X, y_conf, y_sig

def gen_omega(n=3000):
    """Omega: espacial + lunar + contexto tipo Beta (sin sesgo SNT fijo)."""
    fase = RNG.uniform(0, 1, n)
    sicigia = (RNG.random(n) < 0.15).astype(float)
    sch_mean = RNG.normal(7.83, 0.35, n)
    sch_std = RNG.exponential(0.15, n)
    bz = RNG.normal(-1, 6, n)
    kp = RNG.uniform(0, 8, n)
    viento = RNG.uniform(250, 800, n)
    bz_min = bz - RNG.uniform(0, 5, n)
    kp_max = np.clip(kp + RNG.uniform(0, 3, n), 0, 9)
    kp72 = np.clip(kp_max + RNG.normal(0, 1, n), 0, 9)
    pads = RNG.normal(0, 0.5, (n, 2))
    X = np.column_stack([
        fase, sicigia, sch_mean, sch_std, bz, kp, viento,
        bz_min, kp_max, sch_mean, fase, kp72,
    ]).astype(np.float32)
    if X.shape[1] > 12:
        X = X[:, :12]
    elif X.shape[1] < 12:
        X = np.hstack([X, np.zeros((n, 12 - X.shape[1]), dtype=np.float32)])
    y_sig = np.full(n, NEUTRAL, dtype=float)
    y_conf = np.full(n, 0.25)
    mod = (bz < -5) | (kp >= 5)
    sev = (bz < -10) | (kp >= 7)
    y_sig[mod] = WATCH
    y_conf[mod] = 0.55
    y_sig[sev] = ALERT
    y_conf[sev] = 0.75 + np.clip((-bz[sev] - 10) / 40, 0, 0.15)
    sch_anom = np.abs(sch_mean - 7.83) > 0.5
    y_conf[sch_anom] = np.maximum(y_conf[sch_anom], 0.5)
    y_sig[sch_anom & (y_sig < WATCH)] = WATCH
    return X, y_conf, y_sig

if __name__ == '__main__':
    specs = {
        "alfa1": ("alfa1_spaceweather_rf.onnx", gen_alfa1, 10),
        "alfa2": ("alfa2_satellite_cnn.onnx", gen_alfa2, 8),
        "beta1": ("beta1_schumann_fft.onnx", gen_beta1, 16),
        "beta2": ("beta2_atmospheric_cnn.onnx", gen_beta2, 16),
        "delta": ("delta_financial_lstm.onnx", gen_delta, 16),
        "omega": ("omega_espacial_rf.onnx", gen_omega, 12),
    }
    metrics = {}
    for bot, (fname, gen, n_feat) in specs.items():
        print(f"=== {bot} ===")
        X, yc, ys = gen()
        metrics[bot] = train_multioutput(X, yc, ys, n_feat, MODELS_DIR / fname, bot)
    meta = {"version": "1.0.0", "protocol": "physics-informed RF MultiOutputRegressor -> ONNX",
            "output": "[confidence, signal_idx]",
            "signal_map": {"0": "NO_SIGNAL", "1": "NEUTRAL", "2": "WATCH", "3": "ALERT", "4": "BULLISH", "5": "BEARISH"},
            "input_features": {k: v[2] for k, v in specs.items()}, "metrics": metrics}
    (MODELS_DIR / "models_meta.json").write_text(json.dumps(meta, indent=2))
    print("DONE", sorted(p.name for p in MODELS_DIR.iterdir()))
    print(json.dumps(metrics, indent=2))
