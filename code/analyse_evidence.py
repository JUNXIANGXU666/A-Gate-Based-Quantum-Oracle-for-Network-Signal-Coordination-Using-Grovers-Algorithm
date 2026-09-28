"""Publication statistics derived from immutable experiment records."""
from __future__ import annotations

import json
from pathlib import Path
import platform

import numpy as np
from scipy.stats import t

from quantum_oracle import register_costs

ROOT = Path(__file__).resolve().parents[1]


def interval(values):
    x = np.asarray(values, dtype=float)
    mean = float(x.mean())
    half = float(t.ppf(.975, len(x)-1)*x.std(ddof=1)/np.sqrt(len(x)))
    return dict(mean=mean, lo=mean-half, hi=mean+half, n=len(x))


def wilson(success, total):
    z = 1.959963984540054
    p = success/total
    centre = (p+z*z/(2*total))/(1+z*z/total)
    half = z*np.sqrt(p*(1-p)/total+z*z/(4*total*total))/(1+z*z/total)
    return [float(centre-half), float(centre+half)]


def main():
    out = ROOT/'results/statistics'
    out.mkdir(exist_ok=True)
    pq = json.loads((ROOT/'results/pointq_v2/all_results.json').read_text())
    traffic = []
    for case in sorted({v['case'] for v in pq}):
        for baseline in ('synchronised', 'progression'):
            pairs = []
            for seed in range(101,109):
                a = next(v for v in pq if v['case']==case and v['plan']=='optimised' and v['seed']==seed)
                b = next(v for v in pq if v['case']==case and v['plan']==baseline and v['seed']==seed)
                assert a['arrival_hash']==b['arrival_hash']
                pairs.append({key: a[key]-b[key] for key in ('completed_mean_delay','mean_network_queue','throughput_vehicles_hour')})
            traffic.append(dict(case=case, baseline=baseline,
                                difference={k:interval([p[k] for p in pairs]) for k in pairs[0]}))
    (out/'traffic_paired.json').write_text(json.dumps(traffic,indent=2),encoding='utf-8')

    comparisons = json.loads((ROOT/'results/optimisation/all_results.json').read_text())
    opt = []
    for r in comparisons:
        item = {k:r[k] for k in ('case','N','minimum','query_budget','dp_seconds_median')}
        item['methods'] = {}
        for method, runs in r['runs'].items():
            success = sum(x['best']==r['minimum'] for x in runs)
            gaps = [(x['best']-r['minimum'])/r['minimum']*100 for x in runs]
            item['methods'][method] = dict(success=success, n=len(runs), ci95=wilson(success,len(runs)),
                                          median_gap=float(np.median(gaps)), maximum_gap=float(max(gaps)))
            if 'wall_seconds' in runs[0]:
                item['methods'][method]['median_seconds'] = float(np.median([x['wall_seconds'] for x in runs]))
        opt.append(item)
    (out/'optimisation.json').write_text(json.dumps(opt,indent=2),encoding='utf-8')

    files = sorted((ROOT/'results/hardware').glob('counts_repeat_*_seed_*.json'))
    if len(files)!=15:
        print('Traffic and optimisation statistics saved. Hardware incomplete:',len(files))
        return
    rows=[]
    for path in files:
        for r in json.loads(path.read_text()):
            model = json.loads((ROOT/f"results/model/{r['case']}.json").read_text())
            costs,_ = register_costs(model)
            shots=sum(r['counts'].values())
            success=sum(v for k,v in r['counts'].items() if costs[int(k,2)]<=r['K'])
            rows.append({**r,'successes':success,'probability':success/shots,'shot_ci95':wilson(success,shots)})
    summary=[]
    for case,route in sorted({(r['case'],r['route']) for r in rows}):
        a=[v for v in rows if v['case']==case and v['route']==route and v['k']==1]
        b=[v for v in rows if v['case']==case and v['route']==route and v['k']==0]
        a.sort(key=lambda v:(v['repeat'],v['seed_transpiler']))
        b.sort(key=lambda v:(v['repeat'],v['seed_transpiler']))
        assert len(a)==len(b)==15
        excess=[x['probability']-y['probability'] for x,y in zip(a,b)]
        item={k:a[0][k] for k in ('case','route','K','alpha','ideal','logical_qubits','offset_qubits')}
        item.update(probability=interval([v['probability'] for v in a]),baseline=interval([v['probability'] for v in b]),
                    paired_excess=interval(excess), excess_retention=interval([x/(a[0]['ideal']-a[0]['alpha']) for x in excess]),
                    pooled_shots=sum(v['shots'] for v in a),pooled_successes=sum(v['successes'] for v in a),
                    pooled_shot_ci95=wilson(sum(v['successes'] for v in a),sum(v['shots'] for v in a)))
        for key in ('depth','two_qubit_gates','estimated_circuit_seconds'):
            item[key]=[min(v[key] for v in a),max(v[key] for v in a)]
        item['physical_qubits']=[min(len(v['active_physical_qubits']) for v in a),max(len(v['active_physical_qubits']) for v in a)]
        item['single_qubit_gates']=[min(sum(v['operations'].get(k,0) for k in ('rz','sx','x')) for v in a),
                                   max(sum(v['operations'].get(k,0) for k in ('rz','sx','x')) for v in a)]
        item['by_seed']={str(s):interval([v['probability'] for v in a if v['seed_transpiler']==s]) for s in (11,29,47)}
        summary.append(item)
    ledger=json.loads((ROOT/'results/hardware/job_ledger.json').read_text())
    usage=sum(v['actual_quantum_seconds'] for v in ledger)
    assert usage<=600
    document=dict(rows=rows,summary=summary,actual_quantum_seconds=usage,jobs=len(ledger),
                  circuits=len(rows),shots_per_circuit=4096,
                  uncertainty='t intervals across 15 job-layout observations; shot Wilson intervals reported separately',
                  host=dict(processor=platform.processor(),platform=platform.platform()))
    (out/'hardware.json').write_text(json.dumps(document,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print('Actual QPU seconds',usage)


if __name__=='__main__':
    main()
