import re
with open('/home/deamon/workspaces/sentinel_omega/tests/test_pipeline.py', 'r') as f:
    content = f.read()

# Find the duplicate lines and fix
lines = content.split('\n')
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Skip duplicate function signature
    if 'self, mock_mag, mock_wind, mock_kp, mock_eq, mock_fg,' in line and i > 0 and 'def test_geodynamic_runner' in lines[i-2]:
        # Skip this line and the next few duplicate lines
        while i < len(lines) and 'mock_jupiter' not in lines[i] and '):' not in lines[i]:
            i += 1
        if i < len(lines):
            i += 1
        continue
    new_lines.append(line)
    i += 1

with open('/home/deamon/workspaces/sentinel_omega/tests/test_pipeline.py', 'w') as f:
    f.write('\n'.join(new_lines))
print('Fixed')
