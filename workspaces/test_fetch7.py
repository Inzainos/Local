from sentinel_omega.infrastructure.pipeline.data_pipeline import fetch_neo_hazard_summary
import time
start = time.time()
result = fetch_neo_hazard_summary()
elapsed = time.time() - start
print('Time:', elapsed)
print('Result:', result)
