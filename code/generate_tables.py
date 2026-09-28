"""Generate manuscript tables directly from the frozen numerical evidence."""
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript'
OUT.mkdir(exist_ok=True)


def table(caption,label,columns,heading,rows,note=''):
    return '\n'.join([r'\begin{table}[tbp]',r'\centering',r'\caption{\rev{'+caption+'}}',
                      r'\label{'+label+'}',r'{\color{darkred}\small',r'\setlength{\tabcolsep}{4pt}',
                      r'\begin{tabular}{@{}'+columns+'@{}}',r'\toprule',heading+r'\\',r'\midrule',
                      *[row+r'\\' for row in rows],r'\bottomrule',r'\end{tabular}',
                      (r'\par\smallskip\begin{minipage}{\linewidth}\footnotesize '+note+r'\end{minipage}') if note else '',
                      '}',r'\end{table}',''])


def span(v):
    return str(v[0]) if v[0]==v[1] else str(v[0])+'--'+str(v[1])


def main():
    hardware=json.loads((ROOT/'results/statistics/hardware.json').read_text())
    sequence=[('B3-C2','reversible'),('B3-C4','reversible')]+[(f'B{i}-C4','compiled') for i in range(3,7)]
    data=[next(v for v in hardware['summary'] if (v['case'],v['route'])==k) for k in sequence]
    rows=[]
    for v in data:
        d=v['paired_excess']
        rows.append(f"{v['case']} & {'Full' if v['route']=='reversible' else 'Compiled'} & {v['K']} & {v['alpha']:.3f} & {v['baseline']['mean']:.4f} & {v['probability']['mean']:.4f} & [{d['lo']:.4f}, {d['hi']:.4f}]")
    (OUT/'hardware_summary.tex').write_text(table('Hardware probabilities and uncertainty in the paired increase.','tab:hardware-summary','llrrrrl',
        r'Case & Route & \(K\) & \(\alpha\) & \(\widehat P_0\) & \(\widehat P_1\) & 95\% interval for \(\Delta P\)',rows,
        r'B\(n\)-C\(c\) denotes a bidirectional \(n\)-intersection corridor with \(c\) offset levels. Each mean contains 15 executions of 4096 shots. Full denotes the reversible arithmetic oracle. Intervals use paired batch differences.'),encoding='utf-8')
    rows=[]
    for v in data:
        rows.append(f"{v['case']} & {'Full' if v['route']=='reversible' else 'Compiled'} & {v['logical_qubits']} & {span(v['physical_qubits'])} & {span(v['depth'])} & {span(v['single_qubit_gates'])} & {span(v['two_qubit_gates'])}")
    (OUT/'hardware_resources.tex').write_text(table('Resources of the amplified native-gate circuits across the three transpiler seeds.','tab:hardware-resources','llrrrrr',
        r'Case & Route & Logical & Active & Depth & 1Q & 2Q',rows,
        r'Logical and active columns count logical circuit qubits and physical qubits used by operations. 1Q counts native \texttt{rz}, \texttt{sx} and \texttt{x} gates. 2Q counts native \texttt{cz} gates. Measurement and reset are not included in those gate counts.'),encoding='utf-8')
    comparisons=json.loads((ROOT/'results/statistics/optimisation.json').read_text())
    rows=[]
    for v in comparisons:
        m=v['methods']
        rows.append(f"{v['case']} & {v['N']} & {v['query_budget']} & {v['minimum']} & {m['random']['success']} & {m['coordinate']['success']} & {m['quantum_reference']['success']}")
    (OUT/'optimisation_complete.tex').write_text(table('Complete optimisation comparison. Recovery entries count exact minima obtained in 100 independent runs.','tab:optimisation-complete','lrrrrrr',
        r'Case & \(N\) & Budget & Minimum & Random & Coordinate & Grover',rows,
        r'U4, B4 and R4 use eight levels, with the demand multiplier after the hyphen. The remaining B\(n\)-C\(c\) cases use base demand. Grover denotes the ideal-probability adaptive reference. Dynamic programming attains the exact minimum in every case.'),encoding='utf-8')
    rows=[]
    for family in ('U4','B4','R4'):
        for load in (.65,1,1.35,1.55):
            name=f'{family}-{load:g}'
            model=json.loads((ROOT/f'results/model/{name}.json').read_text())
            row=next(v for v in json.loads((ROOT/'results/pointq_v2/all_results.json').read_text()) if v['case']==name and v['plan']=='progression')
            tup=lambda x:'('+','.join(map(str,x))+')'
            rows.append(f"{family} & {load:.2f} & \\({tup(row['offsets'])}\\) & \\({tup(model['exact']['best_offsets'])}\\) & {model['exact']['minimum']} & {model['exact']['conflict_gap']}")
    (OUT/'traffic_plans.tex').write_text(table('Signal plans and exact objective diagnostics for the traffic-simulation scenarios.','tab:traffic-plans','lrllrr',
        r'Network & \(\xi\) & Progression offsets & Table-optimal offsets & \(D_{\min}\) & \(\Gamma\)',rows,
        r'Offsets are level indices with 7.5-s spacing. Equal offsets are \((0,0,0,0)\) in every case. The first minimiser in lexicographic order is used when rounded costs tie.'),encoding='utf-8')

    # Calibration summaries retain provenance in JSON but omit calendar dates in the paper.
    ledger=json.loads((ROOT/'results/hardware/job_ledger.json').read_text())
    active=set(q for v in hardware['rows'] for q in v['active_physical_qubits'])
    calibration={name:[] for name in ('T1','T2','readout_error','cz_error')}
    for record in ledger:
        properties=record['properties_before']
        for q in active:
            for prop in properties['qubits'][q]:
                if prop['name'] in ('T1','T2','readout_error'):
                    value=float(prop['value'])
                    if prop['name'] in ('T1','T2'):
                        value*= {'s':1e6,'ms':1e3,'us':1,'ns':1e-3}[prop['unit']]
                    calibration[prop['name']].append(value)
        for gate in properties['gates']:
            if gate['gate']=='cz' and set(gate['qubits']).issubset(active):
                calibration['cz_error'].extend(float(p['value']) for p in gate['parameters'] if p['name']=='gate_error')
    stats={k:{'median':float(np.median(v)),'min':float(min(v)),'max':float(max(v))} for k,v in calibration.items()}
    (ROOT/'results/statistics/calibration.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    rows=[]
    labels={'T1':r'\(T_1\) (\(\mu\)s)','T2':r'\(T_2\) (\(\mu\)s)','readout_error':'Readout error','cz_error':'CZ gate error'}
    for k,v in stats.items():
        fmt='.2f' if k in ('T1','T2') else '.5f'
        rows.append(f"{labels[k]} & {v['median']:{fmt}} & {v['min']:{fmt}} & {v['max']:{fmt}}")
    (OUT/'calibration.tex').write_text(table('Calibration summaries captured before the execution batches.','tab:calibration','lrrr',
        'Quantity & Median & Minimum & Maximum',rows,
        r'Qubit statistics cover the union of active physical qubits. CZ statistics cover calibrated pairs within that union, including pairs not necessarily traversed by every circuit. Repeated property snapshots may contain the same calibration values.'),encoding='utf-8')
    print('Generated six evidence tables. Calibration:',stats)


if __name__=='__main__':
    main()
