"""Summarise the declared supplementary experiments without selecting outcomes."""
import json
from pathlib import Path

import numpy as np

from analyse_evidence import interval, wilson
from quantum_oracle import register_costs

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/statistics'
METRICS = ('completed_mean_delay','mean_network_queue','throughput_vehicles_hour')
PLANS = ('synchronised','progression','optimised','propagated','bandwidth')


def save(name, data):
    (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf8')


def main():
    OUT.mkdir(exist_ok=True)
    raw = json.loads((ROOT/'results/pointq_extended/combined_results.json').read_text())
    assert len(raw)==640
    rows, comparisons = [], []
    for case in sorted({v['case'] for v in raw}):
        selected = {}
        for plan in PLANS:
            selected[plan] = sorted([v for v in raw if v['case']==case and v['plan']==plan],key=lambda v:v['seed'])
            assert [v['seed'] for v in selected[plan]]==list(range(101,109))
            rows.append(dict(case=case,plan=plan,offsets=selected[plan][0]['offsets'],
                             metrics={k:interval([v[k] for v in selected[plan]]) for k in METRICS}))
        for plan in ('optimised','propagated','bandwidth'):
            for reference in ('progression','synchronised'):
                assert all(a['arrival_hash']==b['arrival_hash'] for a,b in zip(selected[plan],selected[reference]))
                comparisons.append(dict(case=case,plan=plan,reference=reference,
                      difference={k:interval([a[k]-b[k] for a,b in zip(selected[plan],selected[reference])]) for k in METRICS}))
    save('traffic_complete.json',rows)
    save('traffic_extension_paired.json',comparisons)
    print('Base-demand PointQ delay and paired difference from progression')
    for case in ('U4-1','B4-1','R4-1','RC3-1'):
        for plan in PLANS:
            v=next(v for v in rows if v['case']==case and v['plan']==plan)
            diff=next((v['difference']['completed_mean_delay'] for v in comparisons if v['case']==case and v['plan']==plan and v['reference']=='progression'),None)
            print(case,plan,round(v['metrics']['completed_mean_delay']['mean'],4),diff)

    files = sorted((ROOT/'results/hardware_precision').glob('counts_*.json'))
    if len(files)!=2:
        print('Precision hardware statistics deferred until both batches complete.')
        return
    hardware=[]
    for path in files:
        for row in json.loads(path.read_text()):
            table=json.loads((ROOT/f"results/hardware_precision/table_{row['case']}.json").read_text())
            costs,_=register_costs(table)
            success=sum(n for state,n in row['counts'].items() if costs[int(state,2)]<=row['K'])
            hardware.append({**row,'successes':success,'probability':success/row['shots'],
                             'shot_ci95':wilson(success,row['shots'])})
    summary=[]
    for case in ('B3-C2','RC3-C2'):
        a=sorted([v for v in hardware if v['case']==case and v['k']==1],key=lambda v:(v['repeat'],v['seed_transpiler']))
        b=sorted([v for v in hardware if v['case']==case and v['k']==0],key=lambda v:(v['repeat'],v['seed_transpiler']))
        assert len(a)==len(b)==6
        excess=[x['probability']-y['probability'] for x,y in zip(a,b)]
        summary.append(dict(case=case,eta=a[0]['eta'],sum_qubits=a[0]['sum_qubits'],
              logical_qubits=a[0]['logical_qubits'],K=a[0]['K'],alpha=.25,ideal=1,
              baseline=interval([v['probability'] for v in b]),probability=interval([v['probability'] for v in a]),
              paired_excess=interval(excess),excess_retention=interval(np.array(excess)/.75),
              two_qubit_gates=[min(v['two_qubit_gates'] for v in a),max(v['two_qubit_gates'] for v in a)],
              pooled_shot_ci95=wilson(sum(v['successes'] for v in a),sum(v['shots'] for v in a))))
    ledger=json.loads((ROOT/'results/hardware_precision/job_ledger.json').read_text())
    seconds=sum(v['actual_quantum_seconds'] for v in ledger)
    save('hardware_precision.json',dict(rows=hardware,summary=summary,actual_quantum_seconds=seconds,jobs=2,
         uncertainty='Descriptive 95% t intervals across six batch-seed observations (two batches, three transpiler seeds). Initial placements repeat: one distinct for B3-C2, two for RC3-C2.'))
    print('Full-oracle precision diagnostics:',json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
