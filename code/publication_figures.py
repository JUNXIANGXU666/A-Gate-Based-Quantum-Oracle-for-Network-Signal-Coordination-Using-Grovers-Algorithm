"""Reproduce the manuscript figures from archived experimental records."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from scipy.stats import t
from traffic_model import Scenario, link_delay

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'manuscript/figures'
OUT.mkdir(parents=True, exist_ok=True)
arial = Path('C:/Windows/Fonts/arial.ttf')
if arial.exists():
    font_manager.fontManager.addfont(str(arial))
font_manager.findfont('Arial', fallback_to_default=False)
plt.rcParams.update({'font.family':'Arial', 'font.size':9, 'axes.labelsize':9,
    'axes.titlesize':10, 'xtick.labelsize':8, 'ytick.labelsize':8, 'legend.fontsize':8,
    'pdf.fonttype':42, 'ps.fonttype':42, 'axes.spines.top':False, 'axes.spines.right':False,
    'axes.linewidth':.7, 'lines.linewidth':1.5, 'savefig.facecolor':'white'})
INK, BLUE, RED, GREEN = '#4C4C4C', '#0072B2', '#D55E00', '#009E73'
COLORS, STYLES, MARKERS = [INK, RED, BLUE], ['--', '-.', '-'], ['o', 's', '^']
METHODS = ['random', 'coordinate', 'quantum_reference']
METHOD_LABELS = ['Random sampling', 'Coordinate descent', 'Ideal adaptive Grover']
PLANS = ['synchronised', 'progression', 'optimised']
PLAN_LABELS = ['Equal offsets', 'Forward progression', 'Queue-table optimum']

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))

def save(fig, name):
    fig.savefig(OUT/f'{name}.pdf', bbox_inches='tight', pad_inches=.035)
    fig.savefig(OUT/f'{name}.png', dpi=210, bbox_inches='tight', pad_inches=.035)
    plt.close(fig)

def panel(ax, letter, title):
    ax.set_title(f'({letter}) {title}', loc='left', pad=7)

def grid(axes):
    for ax in np.asarray(axes).flat:
        ax.grid(axis='y', color='.9', lw=.6)

def legend(fig, ax):
    fig.legend(*ax.get_legend_handles_labels(), loc='outside upper center', ncol=3, frameon=False)

def networks():
    fig, axes = plt.subplots(1, 3, figsize=(6.5, 1.85), layout='constrained')
    for ax, family, title, letter in zip(axes, ('unidirectional','bidirectional','ring'),
            ('One-way corridor (U4)','Two-way corridor (B4)','Two-way ring (R4)'), 'abc'):
        positions = np.array([[0,.5],[1,.5],[2,.5],[3,.5]])
        if family == 'ring':
            positions = np.array([[.5,1.15],[2.5,1.15],[2.5,-.15],[.5,-.15]])
        for edge in Scenario('network',4,family).links():
            start,end = positions[edge['i']],positions[edge['j']]
            delta = end-start
            normal = np.array([-delta[1],delta[0]])/np.linalg.norm(delta)*(.095 if family!='unidirectional' else 0)
            ax.annotate('',end+normal,start+normal,arrowprops=dict(arrowstyle='-|>',
                color=BLUE if edge['direction']=='forward' else RED,lw=1.6,shrinkA=9,shrinkB=9))
        ax.scatter(*positions.T,s=220,color='white',edgecolor=INK,zorder=4)
        for node,(x,y) in enumerate(positions):
            ax.text(x,y,str(node+1),ha='center',va='center',zorder=5)
        panel(ax,letter,title)
        ax.set(xlim=(-.3,3.3),ylim=(-.65,1.65),aspect='equal')
        ax.axis('off')
    handles=[plt.Line2D([],[],color=BLUE,label='Forward movement'),plt.Line2D([],[],color=RED,label='Reverse movement')]
    fig.legend(handles=handles,loc='outside lower center',ncol=2,frameon=False)
    save(fig,'fig1_networks')

def mechanism():
    fig,axes=plt.subplots(2,2,figsize=(6.5,4.25),sharex=True,sharey='row',layout='constrained')
    scenario=Scenario('B4',4,'bidirectional')
    edge=scenario.links()[0]
    for col,(difference,title) in enumerate(((0,'Equal offsets'),(6,'Downstream green 15 s later'))):
        delay,arrivals,queue=link_delay(scenario,edge,difference,True)
        axes[0,col].step(np.arange(60),arrivals,where='post',color=BLUE,label='Arrivals')
        axes[0,col].step(np.arange(61),np.r_[np.full(36,.5),np.zeros(25)],where='post',color=INK,ls='--',label='Available service')
        axes[1,col].step(np.arange(60),queue,where='post',color=BLUE)
        for row in range(2):
            axes[row,col].axvspan(0,scenario.greens[1],color=GREEN,alpha=.09,lw=0)
            axes[row,col].set_xlim(0,60)
        panel(axes[0,col],'ab'[col],title)
        panel(axes[1,col],'cd'[col],f'Queue delay = {delay:.1f} veh s/cycle')
        axes[1,col].set(xlabel='Time relative to downstream green (s)',xticks=[0,15,30,45,60])
    axes[0,0].set(ylabel='Flow (veh/s)',ylim=(-.02,.57))
    axes[1,0].set(ylabel='Queue (veh)',ylim=(-.06,2.9))
    handles,labels=axes[0,0].get_legend_handles_labels()
    handles.append(plt.Rectangle((0,0),1,1,facecolor=GREEN,alpha=.15,edgecolor='none'))
    fig.legend(handles,labels+['Downstream green'],loc='outside upper center',ncol=3,frameon=False)
    grid(axes)
    save(fig,'fig2_queue_mechanism')

def conflicts():
    fig,axes=plt.subplots(2,3,figsize=(6.5,4.45),sharex=True,sharey='row',layout='constrained')
    ymax=0
    for col,load in enumerate((.65,1,1.35)):
        table=read(f'results/model/B4-{load:g}.json')
        data=np.array(table['continuous'])
        for row,pair in enumerate(((0,1),(2,3))):
            fwd=next(i for i,e in enumerate(table['links']) if (e['i'],e['j'])==pair)
            rev=next(i for i,e in enumerate(table['links']) if (e['j'],e['i'])==pair)
            first,second=data[fwd],data[rev,(-np.arange(8))%8]
            ymax=max(ymax,float((first+second).max()))
            for values,color,label,marker,style in [(first,BLUE,'Forward','o','-'),(second,RED,'Reverse','s','--'),(first+second,INK,'Combined','^',':')]:
                axes[row,col].plot(np.arange(9)*7.5,np.r_[values,values[0]],color=color,marker=marker,ms=3,ls=style,label=label)
            panel(axes[row,col],chr(97+row*3+col),f'Links {pair[0]+1}-{pair[1]+1}, demand {load:.2f}')
            axes[row,col].set(xticks=[0,15,30,45,60],xlim=(0,60))
        axes[1,col].set_xlabel('Relative offset (s)')
    for ax in axes[:,0]:
        ax.set(ylabel='Queue delay (veh s/cycle)',ylim=(0,1.08*ymax))
    grid(axes)
    legend(fig,axes[0,0])
    save(fig,'fig3_offset_conflicts')

def pointq():
    records=read('results/pointq_v2/all_results.json')
    fig,axes=plt.subplots(3,3,figsize=(6.5,6.1),sharex=True,sharey='row',layout='constrained')
    demands=[.65,1,1.35,1.55]
    for col,network in enumerate(('U4','B4','R4')):
        for pi,plan in enumerate(PLANS):
            for row,key in enumerate(('completed_mean_delay','mean_network_queue','throughput_vehicles_hour')):
                if row and plan=='synchronised':
                    continue
                means,errors=[],[]
                for load in demands:
                    paired={v['seed']:v[key] for v in records if v['case']==f'{network}-{load:g}' and v['plan']==plan}
                    assert len(paired)==8
                    if row:
                        baseline={v['seed']:v[key] for v in records if v['case']==f'{network}-{load:g}' and v['plan']=='synchronised'}
                        assert paired.keys()==baseline.keys()
                        values=np.array([paired[seed]-baseline[seed] for seed in sorted(paired)])
                    else:
                        values=np.array(list(paired.values()))
                    means.append(values.mean())
                    errors.append(t.ppf(.975,7)*values.std(ddof=1)/np.sqrt(8))
                positions=np.array(demands)+(.012*(2*pi-3) if row else 0)
                axes[row,col].errorbar(positions,means,yerr=errors,color=COLORS[pi],marker=MARKERS[pi],
                    mfc='white' if pi==1 else COLORS[pi],ls=STYLES[pi],ms=3.5,capsize=2,label=PLAN_LABELS[pi])
        for row in range(3):
            panel(axes[row,col],chr(97+row*3+col),network)
            axes[row,col].set_xticks(demands,['0.65','1.00','1.35','1.55'])
            if row:
                axes[row,col].axhline(0,color=INK,lw=.7,ls=':')
        axes[0,col].set_yscale('log')
        axes[0,col].set_ylim(12,240)
        axes[0,col].set_yticks([15,30,60,120,240],['15','30','60','120','240'])
        axes[0,col].minorticks_off()
        axes[2,col].set_xlabel('Demand multiplier')
    for row,label in enumerate(('Trip delay (s/veh, log scale)','Queue change (veh)','Exit-rate change (veh/h)')):
        axes[row,0].set_ylabel(label)
    grid(axes)
    legend(fig,axes[0,0])
    save(fig,'fig4_pointq_performance')

def optimisation():
    records=read('results/optimisation/all_results.json')
    fig,axes=plt.subplots(2,2,figsize=(6.5,5.2),layout='constrained')
    for col,name in enumerate(('B8-C4','B6-C8')):
        record=next(v for v in records if v['case']==name)
        for i,method in enumerate(METHODS):
            traces=np.array([r['trace'] for r in record['runs'][method]])
            gap=(traces-record['minimum'])/record['minimum']*100
            x=np.arange(1,gap.shape[1]+1)
            axes[0,col].plot(x,np.median(gap,axis=0),color=COLORS[i],ls=STYLES[i],label=METHOD_LABELS[i])
            axes[0,col].fill_between(x,np.quantile(gap,.1,axis=0),np.quantile(gap,.9,axis=0),color=COLORS[i],alpha=.10,lw=0)
        panel(axes[0,col],'ab'[col],f"{name}, {record['N']:,} assignments")
        axes[0,col].set(xlabel='Objective-oracle queries',ylabel='Gap to exact minimum (%)',xscale='log',xlim=(1,gap.shape[1]))
    scale=sorted([v for v in records if v['case'] in ('B3-C4','B4-C4','B5-C4','B6-C4','B8-C4','B6-C8')],key=lambda v:v['N'])
    for i,method in enumerate(METHODS):
        axes[1,0].plot([v['N'] for v in scale],[np.mean([r['best']==v['minimum'] for r in v['runs'][method]])*100 for v in scale],color=COLORS[i],marker=MARKERS[i],ls=STYLES[i],ms=4)
    panel(axes[1,0],'c','Exact-minimum recovery')
    axes[1,0].set(xlabel='Offset assignments',ylabel='Recovery in 100 runs (%)',xscale='log',ylim=(-3,103))
    for i,method in enumerate(METHODS[:2]):
        axes[1,1].plot([v['N'] for v in scale],[1000*np.median([r['wall_seconds'] for r in v['runs'][method]]) for v in scale],color=COLORS[i],marker=MARKERS[i],ls=STYLES[i],ms=4)
    axes[1,1].plot([v['N'] for v in scale],[1000*v['dp_seconds_median'] for v in scale],color=GREEN,marker='D',ms=4,label='Exact dynamic programming')
    panel(axes[1,1],'d','Classical computation')
    axes[1,1].set(xlabel='Offset assignments',ylabel='Measured wall time (ms)',xscale='log',yscale='log')
    axes[1,1].legend(loc='upper left',frameon=False,fontsize=7.5)
    grid(axes)
    legend(fig,axes[0,0])
    save(fig,'fig5_optimisation')

def quantum_verification():
    from quantum_oracle import register_costs
    fig,axes=plt.subplots(1,2,figsize=(6.5,2.8),layout='constrained')
    verification=read('results/quantum/verification_B3-C4.json')
    for alpha,color in ((.0625,BLUE),(.25,RED)):
        k=np.linspace(0,3,241)
        axes[0].plot(k,np.sin((2*k+1)*np.arcsin(np.sqrt(alpha)))**2,color=color,label=f'Feasible fraction {alpha:g}')
        data=[v for v in verification['amplification'] if v['alpha']==alpha]
        axes[0].plot([v['k'] for v in data],[v['observed'] for v in data],'o',mfc='white',mec=color,ms=5)
    panel(axes[0],'a','Full-oracle noiseless verification')
    axes[0].set(xlabel='Grover iterations',ylabel='Feasible-state probability',xticks=[0,1,2,3],ylim=(-.04,1.02))
    axes[0].legend(loc='upper center',bbox_to_anchor=(.5,-.25),frameon=False,fontsize=7.5)
    costs,_=register_costs(read('results/model/B3-C4.json'))
    good=costs<=253
    ideal=np.where(good,.78125/good.sum(),(1-.78125)/(16-good.sum()))
    rows=read('results/statistics/hardware.json')['rows']
    x=np.arange(16)
    for route,color,shift,label in [('reversible',INK,-.18,'Full oracle'),('compiled',BLUE,.18,'Compiled phase')]:
        observations=[r for r in rows if r['case']=='B3-C4' and r['route']==route and r['k']==1]
        shots=sum(sum(r['counts'].values()) for r in observations)
        values=[sum(r['counts'].get(format(j,'04b'),0) for r in observations)/shots for j in range(16)]
        axes[1].bar(x+shift,values,.36,color=color,label=label)
    axes[1].plot(x,ideal,'D',color=RED,ms=3.5,label='Ideal')
    panel(axes[1],'b','IBM distribution, same marked states')
    axes[1].set(xlabel='Encoded assignment',ylabel='Probability',xticks=[0,3,6,9,12,15],ylim=(0,.42))
    axes[1].legend(loc='upper right',frameon=False,fontsize=7.5)
    save(fig,'fig6_oracle_verification')

def hardware():
    document=read('results/statistics/hardware.json')
    sequence=[('B3-C2','reversible'),('B3-C4','reversible')]+[(f'B{i}-C4','compiled') for i in range(3,7)]
    summaries=[next(v for v in document['summary'] if (v['case'],v['route'])==identity) for identity in sequence]
    fig=plt.figure(figsize=(7.2,4.55),layout='constrained')
    layout=fig.add_gridspec(2,2,width_ratios=[1.05,1],height_ratios=[3.2,1])
    axes=[fig.add_subplot(layout[:,0]),fig.add_subplot(layout[0,1]),fig.add_subplot(layout[1,1])]
    for index,record in enumerate(summaries):
        x=np.mean(record['two_qubit_gates'])
        y=record['excess_retention']['mean']
        full=record['route']=='reversible'
        axes[0].errorbar(x,y,xerr=[[x-record['two_qubit_gates'][0]],[record['two_qubit_gates'][1]-x]],
            yerr=[[y-record['excess_retention']['lo']],[record['excess_retention']['hi']-y]],
            color=RED if full else BLUE,marker='s' if full else 'o',capsize=2,ms=5)
        offsets=[(0,-20),(-4,13),(6,0),(-14,18),(5,35),(16,24)]
        axes[0].annotate(record['case']+(' full' if full else ''),(x,y),xytext=offsets[index],textcoords='offset points',
            ha='right' if index==1 else 'left' if index==2 else 'center',fontsize=7.5,
            arrowprops=dict(arrowstyle='-',lw=.5,color='.5') if index in (0,4,5) else None)
    axes[0].axhline(0,color=INK,lw=.8,ls='--')
    axes[0].set(xlabel='Transpiled two-qubit gates',ylabel='Excess-retention ratio',xscale='log',xlim=(25,110000),ylim=(-.12,.66))
    panel(axes[0],'a','Retention and circuit burden')
    axes[0].plot([],[],'s',color=RED,label='Full reversible')
    axes[0].plot([],[],'o',color=BLUE,label='Compiled phase')
    axes[0].legend(loc='upper right',frameon=False,fontsize=7.5)
    def paired_points(ax, row, identity, show_labels=False):
        for si,seed in enumerate((11,29,47)):
            increases=[]
            for repeat in range(1,6):
                pair=[v for v in document['rows'] if (v['case'],v['route'])==identity and v['repeat']==repeat and v['seed_transpiler']==seed]
                increases.append(next(v['probability'] for v in pair if v['k']==1)-next(v['probability'] for v in pair if v['k']==0))
            ax.scatter(increases,row+(si-1)*.16+np.linspace(-.06,.06,5),color=COLORS[si],
                s=11,marker=MARKERS[si],alpha=.8,label=f'Seed {seed}' if show_labels else None)
        stats=summaries[sequence.index(identity)]['paired_excess']
        ax.errorbar(stats['mean'],row+.36,xerr=[[stats['mean']-stats['lo']],[stats['hi']-stats['mean']]],
            color='black',marker='|',ms=6,capsize=2,lw=1.1)

    near_baseline=[identity for identity in sequence if identity!=('B3-C4','compiled')]
    for row,identity in enumerate(near_baseline):
        paired_points(axes[1],row,identity,show_labels=row==0)
    axes[1].axvline(0,color=INK,lw=.8,ls='--')
    axes[1].set(xlabel='Paired probability increase',yticks=np.arange(5),
        yticklabels=['B3-C2 full','B3-C4 full','B4-C4 compiled','B5-C4 compiled','B6-C4 compiled'],
        ylim=(4.65,-.45),xlim=(-.04,.065),xticks=[-.04,-.02,0,.02,.04,.06])
    axes[1].tick_params(axis='y',labelsize=7.5)
    axes[1].tick_params(axis='x',labelsize=7)
    panel(axes[1],'b','Near-baseline cases (zoom)')
    paired_points(axes[2],0,('B3-C4','compiled'))
    axes[2].set(xlabel='Paired probability increase',yticks=[],ylim=(.65,-.45),xlim=(.18,.47),xticks=[.2,.3,.4])
    panel(axes[2],'c','B3-C4 compiled')
    axes[2].legend(*axes[1].get_legend_handles_labels(),loc='upper center',
        bbox_to_anchor=(.5,-.65),ncol=3,frameon=False,fontsize=7,handletextpad=.25,columnspacing=.9)
    save(fig,'fig7_hardware_boundary')

if __name__=='__main__':
    networks()
    mechanism()
    conflicts()
    pointq()
    optimisation()
    quantum_verification()
    hardware()
