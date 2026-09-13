from sentinel_omega.infrastructure.pipeline.data_pipeline import compute_lunar_phase_series
import time
start = time.time()
result = compute_lunar_phase_series(days=30)
elapsed = time.time() - start
print('Time:', elapsed)
print('Result:', result)
