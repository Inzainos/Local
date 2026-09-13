from sentinel_omega.infrastructure.pipeline.data_pipeline import fetch_lod_series
import time
start = time.time()
result = fetch_lod_series(days=90)
elapsed = time.time() - start
print('Time:', elapsed)
print('Result:', result)
