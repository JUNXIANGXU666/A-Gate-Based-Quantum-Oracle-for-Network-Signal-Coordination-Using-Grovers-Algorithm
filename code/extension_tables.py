"""Tables for profile sensitivity, mapped benchmark and precision diagnostics."""
import json
from pathlib import Path

from generate_tables import table, span

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript'


def read(name):
    return json.loads((ROOT/name).read_text())


def write(name, text):
    (OUT/name).write_text(text,encoding='utf8')


def offsets(x):
    return r'\(\mathtt{'+''.join(map(str,x))+r'}\)'


def estimate(x, digits=3):
    return f"{x['mean']:.{digits}f} [{x['lo']:.{digits}f}, {x['hi']:.{digits}f}]"


def compact_table(caption,label,columns,heading,rows,note=''):
    return table(caption,label,columns,heading,rows,note).replace(r'{\color{darkred}\small',r'{\color{darkred}\footnotesize').replace('{4pt}','{3pt}')


def main():
    OUT.mkdir(exist_ok=True)
    hw=read('results/statistics/hardware.json')['summary']
    sequence=[('B3-C2','reversible'),('B3-C4','reversible')]+[(f'B{i}-C4','compiled') for i in range(3,7)]
    hw=[next(v for v in hw if (v['case'],v['route'])==key) for key in sequence]
    route=lambda v:'Full' if v['route']=='reversible' else 'Compiled'
    first=[f"{v['case']} & {route(v)} & {v['K']} & {v['alpha']:.3f} & {v['ideal']:.4f} & {v['baseline']['mean']:.4f} & {v['probability']['mean']:.4f}"+r'\\' for v in hw]
    second=[f"{v['case']} & {route(v)} & {estimate(v['paired_excess'],4)} & {estimate(v['excess_retention'],4)}"+r'\\' for v in hw]
    text='\n'.join([r'\begin{table}[H]\centering',
       r'\caption{\rev{Hardware success probabilities and paired excess amplification.}}\label{tab:hardware-summary}',
       r'{\color{darkred}\small\setlength{\tabcolsep}{4pt}',
       r'\begin{tabular}{@{}llrrrrr@{}}\toprule',
       r'Case & Route & \(K\) & \(\alpha\) & \(P_1^{\mathrm{ideal}}\) & \(\widehat P_0\) & \(\widehat P_1\)\\\midrule',
       *first,r'\bottomrule\end{tabular}\par\medskip',
       r'\begin{tabular}{@{}llll@{}}\toprule',
       r'Case & Route & \(\Delta P\) [95\% interval] & \(R_{\mathrm{ex}}\) [95\% interval]\\\midrule',
       *second,r'\bottomrule\end{tabular}',
       r'\par\smallskip\begin{minipage}{\linewidth}\footnotesize B\(n\)-C\(c\) denotes a bidirectional \(n\)-intersection corridor with \(c\) offset levels. Each mean uses 15 executions of 4096 shots. Full denotes the arithmetic oracle at cost resolution \(\eta=1\). Intervals describe the paired batch--layout observations.\end{minipage}}',r'\end{table}',''])
    write('hardware_summary.tex',text)

    rows=[]
    for v in read('results/statistics/optimisation.json'):
        directory='resco' if v['case'].startswith('RC3') else 'model'
        model=read(f"results/{directory}/{v['case']}.json")
        m=v['methods']
        rows.append(f"{v['case']} & {v['N']} & {v['query_budget']} & {v['minimum']} & {model['exact']['conflict_gap']} & {offsets(model['exact']['best_offsets'])} & {m['random']['success']} & {m['coordinate']['success']} & {m['quantum_reference']['success']}")
    write('optimisation_complete.tex',compact_table('Exact objective diagnostics and minimum recovery under matched query budgets.','tab:optimisation-complete','lrrrrlrrr',
          r'Case & \(N\) & Budget & \(D_{\min}\) & \(\Gamma\) & Offsets & Random & CD & Grover',rows,
          r'Each offset string lists one level index per intersection, including the fixed zero reference. U4, B4 and R4 use eight levels, with demand after the hyphen. RC3-1 uses eight levels at base demand. B\(n\)-C\(c\) and RC3-C\(c\) use base demand and \(c\) levels. CD denotes coordinate descent. Recovery counts are out of 100. Grover is the ideal-probability reference. Dynamic programming attains every minimum. At \(\eta=1\), multiplying \(D_{\min}\) or \(\Gamma\) by one vehicle-second per cycle gives the physical cost scale.'))

    plans=read('results/traffic_extension/all_plans.json')
    rows=[]
    iteration=[]
    for v in plans:
        name=v['case']
        family,load=name.split('-')
        directory='resco' if family=='RC3' else 'model'
        model=read(f'results/{directory}/{name}.json')
        c=v['frozen_costs']
        rows.append(f"{family} & {float(load):.2f} & {offsets(v['plans']['progression'])} & {offsets(v['plans']['optimised'])} & {c['synchronised']} & {c['progression']} & {c['optimised']} & {model['exact']['conflict_gap']}")
        p=v['propagation']
        iteration.append(f"{name} & {offsets(v['plans']['propagated'])} & {offsets(v['plans']['bandwidth'])} & {p['iterations']} & {'Fixed plan' if p['status']=='fixed_point' else 'Cycle detected' if p['status']=='cycle_detected' else 'Limit'}")
    write('traffic_plans.tex',compact_table('Reference and optimal plans evaluated under the initial queue-table objective.','tab:traffic-plans','lrllrrrr',
          r'Network & \(\xi\) & Progression & Table optimum & \(D_{\mathrm{eq}}\) & \(D_{\mathrm{prog}}\) & \(D_{\min}\) & \(\Gamma\)',rows,
          r'Each digit in an offset string is one node offset in 7.5-s units. Equal offsets are all zero. \(D_{\mathrm{eq}}\) and \(D_{\mathrm{prog}}\) evaluate the equal-offset and progression plans using the same initial tables. Costs and conflict gaps are shown on the vehicle-second-per-cycle scale because \(\eta=1\). Tied minima use lexicographic order.'))
    write('profile_plans.tex',table('Additional signal plans and termination of the profile-update iteration.','tab:profile-plans','lllr l',
          r'Case & Updated profiles & Bandwidth & Updates & Termination',iteration,
          r'Offset strings use the same convention as Table~\ref{tab:traffic-plans}. On a cycle, the last distinct input plan is returned. An unchanged plan is a fixed point of this update rule, not a certificate of global network-delay optimality.'))

    labels={'synchronised':'Equal','progression':'Progression','optimised':'Initial tables','propagated':'Updated profiles','bandwidth':'Bandwidth'}
    measurements=read('results/statistics/traffic_complete.json')
    rows=[]
    for p in plans:
        for index,plan in enumerate(labels):
            v=next(v for v in measurements if v['case']==p['case'] and v['plan']==plan)
            m=v['metrics']
            case=p['case'] if index==0 else ''
            rows.append(f"{case} & {labels[plan]} & {estimate(m['completed_mean_delay'],2)} & {estimate(m['mean_network_queue'],2)} & {estimate(m['throughput_vehicles_hour'],1)}"+r'\\')
        rows.append(r'\addlinespace[3pt]')
    heading=r'Case & Plan & Delay (s/veh) & Mean queue (veh) & Exits (veh/h)\\'
    write('traffic_complete.tex','\n'.join([r'\begingroup\color{darkred}\footnotesize\setlength{\tabcolsep}{3pt}',
        r'\begin{longtable}{@{}llrrr@{}}',
        r'\caption{PointQ means and 95\% intervals across eight paired arrival seeds.}\label{tab:traffic-complete}\\',
        r'\toprule',heading,r'\midrule\endfirsthead',r'\toprule',heading,r'\midrule\endhead',
        r'\bottomrule\endfoot',*rows,r'\end{longtable}\endgroup','']))

    precision=read('results/statistics/hardware_precision.json')['summary']
    rows=[]
    for v in precision:
        rows.append(f"{v['case']} & {v['eta']} & {v['sum_qubits']} & {span(v['two_qubit_gates'])} & {v['baseline']['mean']:.4f} & {v['probability']['mean']:.4f} & {estimate(v['excess_retention'])}")
    write('hardware_precision.tex',compact_table('Cost-resolution diagnostics using the full reversible oracle.','tab:hardware-precision','lrrrrrl',
        r'Case & \(\eta\) & Sum qubits & 2Q & \(\widehat P_0\) & \(\widehat P_1\) & \(R_{\mathrm{ex}}\) [95\% interval]',rows,
        r'Both cases use two offset qubits, \(\alpha=0.25\) and \(P_1^{\mathrm{ideal}}=1\). Each probability averages six observations from two batches and three transpiler seeds. \(\eta\) is in vehicle-seconds per cycle. Every fine-table minimum remains marked at the stated coarser resolution, as verified by enumeration. This marked-set agreement is instance-specific.'))
    rows=[]
    for v in hw+precision:
        description=route(v) if 'route' in v else f"Full, $\\eta={v['eta']}$"
        ci=v['pooled_shot_ci95']
        rows.append(f"{v['case']} & {description} & [{ci[0]:.4f}, {ci[1]:.4f}]")
    write('hardware_shot_intervals.tex',table('Pooled finite-shot Wilson intervals for one-iteration success probability.','tab:hardware-shot-intervals','lll',
        r'Case & Circuit & 95\% Wilson interval',rows,
        r'The main-suite rows pool 61,440 shots each. Precision rows pool 24,576 shots each. These intervals describe binomial counting uncertainty conditional on treating the pooled observations as a common probability. They do not replace the batch--layout intervals, which also reflect observed execution variation.'))
    print('Generated supplementary tables, including all 80 traffic scenario-plan rows.')


if __name__=='__main__':
    main()
