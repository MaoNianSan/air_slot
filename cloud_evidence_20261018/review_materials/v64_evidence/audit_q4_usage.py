from pathlib import Path
from collections import Counter
import json
import pandas as pd

repo=Path('D:/research/air_slot/code/explore')
out={}
def summarize(rows):
    times=[str(x['decision_time']) for x in rows]
    return dict(rows=len(rows),episodes=len({x['episode_id'] for x in rows}),date_min=min(times),date_max=max(times),months=dict(sorted(Counter(t[:7] for t in times).items())))
for rel in ['final_test/FINAL_TEST_SHARED_NODE_INPUTS.parquet','final_test/exp2/data/EXP2A_NODE_RECORDS.parquet','final_test/exp4/EXP4_CANONICAL_EVENTS.parquet']:
    p=repo/'artifacts/experiment'/rel
    out[str(p)]=summarize(pd.read_parquet(p,columns=['decision_time','episode_id']).to_dict('records'))
for p in (repo/'artifacts/experiment').glob('final_test*/checkpoints/CANONICAL_NODES.json'):
    d=json.loads(p.read_text(encoding='utf-8'))['payload']
    if d.get('nodes'):
        out[str(p)]=summarize(d['nodes'])
out['paper_formal_access_counts']={str(y):json.loads((repo/f'data2/reports/paper_formal/{y}/PAPER_FORMAL_MANIFEST.json').read_text())['final_test_access_count'] for y in range(2017,2023)}
dest=Path(__file__).with_name('q4_usage_audit_20261015.json')
dest.write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2))
