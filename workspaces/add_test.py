with open('/home/deamon/workspaces/sentinel_omega/tests/test_pipeline.py', 'r') as f:
    content = f.read()

insert_marker = 'class TestLegacyDataLoader:'
insert_idx = content.find(insert_marker)
if insert_idx == -1:
    print(Insert
