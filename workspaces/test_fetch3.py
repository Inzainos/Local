from sentinel_omega.infrastructure.pipeline.data_pipeline import fetch_schumann_resonance
import time
start = time.time()
result = fetch_schumann_resonance(cleanup=True)
elapsed = time.time() - start
print('Time:', elapsed)
print('Result:', result)
