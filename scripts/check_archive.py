"""Offline consistency checks for the released scientific evidence."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'code'))
from traffic_model import Scenario, assignments, evaluate
from quantum_oracle import register_costs

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))

manifest=read('MANIFEST.json')
for relative,entry in manifest.items():
    data=(ROOT/relative).read_bytes()
    assert len(data)==entry['bytes']
    assert hashlib.sha256(data).hexdigest()==entry['sha256'],relative
cases=0
for path in (ROOT/'results/model').glob('*.json'):
    if path.name=='summary.json':
        continue
    table=json.loads(path.read_text())
    costs=evaluate(table,assignments(Scenario(**table['scenario'])))
    assert int(costs.min())==table['exact']['minimum'],path.name
    cases+=1
assert cases==19
traffic=read('results/pointq_v2/all_results.json')
assert len(traffic)==288
pairs={}
for row in traffic:
    assert row['all_arrivals']-row['all_exits']==row['unfinished_vehicles']
    assert row['ending_queue']<=row['unfinished_vehicles']
    assert pairs.setdefault((row['case'],row['seed']),row['arrival_hash'])==row['arrival_hash']
hardware=[]
for path in (ROOT/'results/hardware').glob('counts_repeat_*_seed_*.json'):
    for row in json.loads(path.read_text()):
        assert sum(row['counts'].values())==row['shots']==4096
        costs,_=register_costs(read(f"results/model/{row['case']}.json"))
        assert np.isclose((costs<=row['K']).mean(),row['alpha'])
        hardware.append(row)
assert len(hardware)==180
ledger=read('results/hardware/job_ledger.json')
assert len(ledger)==15 and all(row['status']=='DONE' for row in ledger)
assert sum(row['actual_quantum_seconds'] for row in ledger)==495
assert {r['job_id'] for r in hardware}=={r['job_id'] for r in ledger}
assert len(read('results/hardware/isa_verification.json'))==12
print(f'PASS: {len(manifest)} file hashes; 19 exact objectives; 288 paired traffic records; 180 hardware count records; 15 completed IBM jobs.')
