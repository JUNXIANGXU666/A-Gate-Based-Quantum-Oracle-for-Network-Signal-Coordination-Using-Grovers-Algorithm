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
    assert len(data)==entry['bytes'],relative
    assert hashlib.sha256(data).hexdigest()==entry['sha256'],relative
cases=0
for folder in ('model','resco'):
    for path in (ROOT/'results'/folder).glob('*.json'):
        table=json.loads(path.read_text())
        if 'scenario' not in table or 'exact' not in table:
            continue
        costs=evaluate(table,assignments(Scenario(**table['scenario'])))
        assert int(costs.min())==table['exact']['minimum'],path.name
        assert np.array_equal(np.load(path.with_suffix('.npz'))['costs'],costs),path.name
        cases+=1
assert cases==25
traffic=read('results/pointq_extended/combined_results.json')
assert len(traffic)==640
pairs={}
seen=set()
for row in traffic:
    assert row['all_arrivals']-row['all_exits']==row['unfinished_vehicles']
    assert row['ending_queue']<=row['unfinished_vehicles']
    assert pairs.setdefault((row['case'],row['seed']),row['arrival_hash'])==row['arrival_hash']
    key=row['case'],row['plan'],row['seed']
    assert key not in seen,key
    seen.add(key)
assert len({r['case'] for r in traffic})==16
assert len(read('results/pointq_v2/event_provenance.json'))==288
assert len(read('results/pointq_extended/event_provenance.json'))==352
plans=read('results/traffic_extension/all_plans.json')
assert len(plans)==16
for record in plans:
    for row in [r for r in traffic if r['case']==record['case']]:
        assert row['offsets']==record['plans'][row['plan']]
optimisation=read('results/optimisation_extended/combined_results.json')
assert len(optimisation)==19
for row in optimisation:
    assert all(len(runs)==100 for runs in row['runs'].values())
    folder='resco' if row['case'].startswith('RC3') else 'model'
    assert row['minimum']==read(f"results/{folder}/{row['case']}.json")['exact']['minimum']
hardware=[]
for group in ('hardware','hardware_precision'):
    for path in (ROOT/'results'/group).glob('counts_*.json'):
        for row in json.loads(path.read_text()):
            assert sum(row['counts'].values())==row['shots']==4096
            source=(f"results/model/{row['case']}.json" if group=='hardware'
                    else f"results/hardware_precision/table_{row['case']}.json")
            costs,_=register_costs(read(source))
            assert np.isclose((costs<=row['K']).mean(),row['alpha'])
            hardware.append(row)
assert len(hardware)==204
ledger=read('results/hardware/job_ledger.json')+read('results/hardware_precision/job_ledger.json')
assert len(ledger)==17 and all(row['status']=='DONE' for row in ledger)
assert sum(row['actual_quantum_seconds'] for row in ledger)==525
assert {r['job_id'] for r in hardware}=={r['job_id'] for r in ledger}
assert len(read('results/hardware/isa_verification.json'))==12
assert len(read('results/hardware_precision/isa_verification.json'))==12
checks=0
for group in ('quantum','hardware_precision'):
    for path in (ROOT/'results'/group).glob('verification_*.json'):
        record=json.loads(path.read_text())
        checks+=record['sum_basis_checks']+record['bit_phase_basis_checks']
        assert max(record['errors'].values())<1e-12
assert checks==228,checks
for name,folder in [('B3-C2','model'),('RC3-C2','resco')]:
    fine,_=register_costs(read(f'results/{folder}/{name}.json'))
    coarse,_=register_costs(read(f'results/hardware_precision/table_{name}.json'))
    assert np.array_equal(fine==fine.min(),coarse==coarse.min())
print(f'PASS: {len(manifest)} file hashes; 25 exact table instances; 19 optimisation cases; '
      '640 paired traffic records; 204 hardware records; 17 completed IBM jobs; 228 basis tests.')
