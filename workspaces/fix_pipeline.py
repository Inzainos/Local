with open('/home/deamon/workspaces/sentinel_omega/tests/test_pipeline.py', 'r') as f:
    content = f.read()

# Find the start and end of the broken test function
start_marker = 'def test_geodynamic_runner('
end_marker = 'runner = GeodynamicLayerRunner(enable_satellite=False)'

# Find all occurrences
start_idx = content.find(start_marker)
if start_idx == -1:
    print(Start
