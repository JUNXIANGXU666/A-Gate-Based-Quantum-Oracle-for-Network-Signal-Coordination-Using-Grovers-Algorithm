"""Classical baselines and an ideal-probability model of adaptive Grover search."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

import numpy as np

from quantum_oracle import register_costs
from traffic_model import evaluate


ROOT=Path(__file__).resolve().parents[1]


def exact_path_or_ring(table):
    C,n=table["scenario"]["states"],table["scenario"]["n"]
    rows=np.asarray(table["integer"])
    edge_cost={}
    for e,edge in enumerate(table["links"]):
        i,j=edge["i"],edge["j"]
        key=tuple(sorted((i,j)))
        pair=edge_cost.setdefault(key,np.zeros((C,C),dtype=int))
        for u in range(C):
            for v in range(C):
                pair[u,v]+=rows[e,(u-v if i<j else v-u) % C]
    value=np.full(C,np.inf)
    value[0]=0
    parents=[]
    for i in range(n-1):
        candidate=value[:,None]+edge_cost[(i,i+1)]
        parents.append(candidate.argmin(axis=0))
        value=candidate.min(axis=0)
    if (0,n-1) in edge_cost:
        value+=edge_cost[(0,n-1)][0,:]
    end=int(np.argmin(value))
    best=int(value[end])
    offsets=[end]
    for parent in parents[::-1]:
        offsets.append(int(parent[offsets[-1]]))
    offsets=offsets[::-1]
    assert evaluate(table,offsets)==best
    return best,offsets


def classical(table, costs, offsets, budget, seed, method):
    rng=np.random.default_rng(seed)
    C,n=table["scenario"]["states"],table["scenario"]["n"]
    q=int(math.log2(C))
    queries=0
    best=math.inf
    trace=[]
    started=time.perf_counter()
    def sample(x):
        nonlocal queries,best
        value=int(evaluate(table,x))
        queries+=1
        best=min(best,value)
        trace.append(best)
        return value
    while queries<budget:
        x=offsets[int(rng.integers(len(costs)))].copy()
        value=sample(x)
        if method=="random":
            continue
        improved=True
        while improved and queries<budget:
            improved=False
            for node in rng.permutation(np.arange(1,n)):
                current=int(x[node])
                selected=current
                for option in range(C):
                    if queries>=budget:
                        break
                    if option==current:
                        continue
                    x[node]=option
                    candidate=sample(x)
                    if candidate<value:
                        value,selected=candidate,option
                        improved=True
                x[node]=selected
    return {"best":int(best),"queries":queries,"trace":trace,"wall_seconds":time.perf_counter()-started}


def adaptive_quantum_reference(costs,budget,seed):
    rng=np.random.default_rng(seed)
    N=len(costs)
    index=int(rng.integers(N))
    best=int(costs[index])
    queries=1
    m=1.0
    trace=[best]
    updates=0
    while queries<budget:
        trial=int(rng.integers(N))
        queries+=1
        if costs[trial]<best:
            best=int(costs[trial])
            m=1.0
            updates+=1
            trace.append(best)
            continue
        trace.append(best)
        k=int(rng.integers(math.ceil(m)))
        if queries+k+1>budget:
            break
        good=np.flatnonzero(costs<best)
        alpha=len(good)/N
        p=float(np.sin((2*k+1)*np.arcsin(np.sqrt(alpha)))**2)
        if rng.random()<p:
            candidate=int(costs[int(rng.choice(good))])
            assert candidate<best
            best=candidate
            m=1.0
            updates+=1
        else:
            m=min(1.2*m,np.sqrt(N))
        trace.extend([trace[-1]]*k+[best])
        queries+=k+1
    trace.extend([best]*(budget-len(trace)))
    return {"best":best,"queries":queries,"trace":trace,"updates":updates,
            "model":"ideal Grover probability, unknown-M adaptive schedule, no gate-runtime claim"}


def main():
    folder=ROOT/"results/optimisation"
    folder.mkdir(parents=True,exist_ok=True)
    all_rows=[]
    names=[f"{n}-{load:g}" for n in ("U4","B4","R4") for load in (0.65,1,1.35)]
    names += ["B3-C4","B4-C4","B5-C4","B6-C4","B8-C4","B6-C8"]
    for name in names:
        target=folder/f"{name}.json"
        if target.exists():
            all_rows.append(json.loads(target.read_text()))
            continue
        table=json.loads((ROOT/f"results/model/{name}.json").read_text())
        costs,offsets=register_costs(table)
        timings=[]
        for _ in range(20):
            t=time.perf_counter()
            exact,x=exact_path_or_ring(table)
            timings.append(time.perf_counter()-t)
        assert exact==int(costs.min())
        budget=max(16,int(8*np.ceil(np.sqrt(len(costs)))))
        experiments={method:[] for method in ("random","coordinate","quantum_reference")}
        for seed in range(100):
            for method in ("random","coordinate"):
                experiments[method].append(classical(table,costs,offsets,budget,seed,method))
            experiments["quantum_reference"].append(adaptive_quantum_reference(costs,budget,seed))
        row={"case":name,"N":len(costs),"query_budget":budget,"minimum":exact,"dp_offsets":x,
             "dp_seconds_median":float(np.median(timings)),"runs":experiments}
        target.write_text(json.dumps(row),encoding="utf-8")
        all_rows.append(row)
        print(name,budget,{m:sum(r["best"]==exact for r in results) for m,results in experiments.items()},flush=True)
    (folder/"all_results.json").write_text(json.dumps(all_rows),encoding="utf-8")


if __name__=="__main__":
    main()
