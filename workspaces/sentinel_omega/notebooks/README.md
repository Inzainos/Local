# Sentinel Omega — Jupyter Notebooks

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_jupyter.txt
```

### 2. Launch Jupyter

```bash
jupyter lab
```

Or:

```bash
jupyter notebook
```

### 3. Open `jupyter_launcher.ipynb`

Run cells sequentially:

1. **Setup & Imports** — Configure environment, disable Telegram
2. **Initialize ONNX Models** — Load all 5 bot models (alfa1, alfa2, beta1, beta2, delta)
3. **Initialize Database** — Create SQLite schema
4. **Run Single Cycle** — Execute one iteration
5. **Run Multiple Cycles** — Real-time monitoring (5 cycles recommended for testing)
6. **Query Results** — Fetch detections & cycle data
7. **Visualize** — Plot performance metrics
8. **Shutdown** — Clean up resources

## Key Features

✅ **ONNX-Only Models** — All 5 bots use ONNX Runtime (GPU/CPU optimized)  
✅ **No Telegram** — Alerts only logged to database  
✅ **Real-time Monitoring** — Live cycle execution in Jupyter  
✅ **Interactive Plots** — Matplotlib + Plotly visualizations  
✅ **SQL Queries** — Direct database access via Repository class  

## Environment Variables

```bash
# Disable Telegram
export JUPYTER_ENABLED=true
export JUPYTER_DISABLE_TELEGRAM=true

# ONNX Runtime
export ONNX_USE_GPU=true  # false for CPU-only
```

## Model Files

Place all `.onnx` files in `sentinel_omega/models/`:

```
sentinel_omega/models/
├── alfa1_spaceweather_rf.onnx       (10 inputs → 2 outputs)
├── alfa2_satellite_cnn.onnx         (512 inputs → 3 outputs)
├── beta1_schumann_fft.onnx          (256 inputs → 4 outputs)
├── beta2_atmospheric_cnn.onnx       (64 inputs → 3 outputs)
└── delta_financial_lstm.onnx        (32 inputs → 2 outputs)
```

If models are not found, the system will use mock ONNX sessions for testing.

## Troubleshooting

### ONNX Runtime Not Installed

```bash
pip install onnxruntime
# For GPU support:
pip install onnxruntime-gpu
```

### Database Lock

Delete `sentinel_omega/data/SENTINEL_OMEGA_PRO.db` and restart.

### Models Not Loading

Check that `.onnx` files exist in `sentinel_omega/models/`.

## Performance

- **Per-cycle time**: ~30-60s (depends on API responses)
- **Model inference**: ~100-500ms per model (ONNX Runtime)
- **Database write**: ~50-100ms per cycle

## Next Steps

- Deploy to **JupyterHub** for multi-user access
- Configure **Papermill** for scheduled notebook execution
- Enable **Telegram alerts** via environment variables (optional)
- Export results to **Cloud Storage** (S3, GCS, etc.)
