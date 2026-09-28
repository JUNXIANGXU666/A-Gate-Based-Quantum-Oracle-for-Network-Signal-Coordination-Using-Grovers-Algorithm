from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

from quantum_oracle import cost_computation, grover, register_costs, reversible_oracle


ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = AerSimulator(method="statevector",max_parallel_threads=4)


def run(circuits):
    compiled = transpile(circuits,SIMULATOR,optimization_level=0)
    result = SIMULATOR.run(compiled).result()
    assert result.success
    return [np.asarray(result.data(i)["statevector"]) for i in range(len(circuits))]


def verify(table, name):
    costs,offsets = register_costs(table)
    N = len(costs)
    thresholds = sorted(set([int(costs.min())-1,int(costs.min()),int(np.sort(costs)[max(0,N//4-1)]),int(costs.max())]))
    circuits, expected, tags = [], [], []
    compute,meta = cost_computation(table)
    nq = meta["offset_qubits"]
    for state in range(N):
        c = QuantumCircuit(compute.num_qubits)
        for j in range(nq):
            if state>>j&1:
                c.x(j)
        c.compose(compute,inplace=True)
        c.save_statevector()
        target = state+((int(costs[state])-meta["base"])//meta["divisor"] << nq)
        circuits.append(c)
        expected.append((target,1.0))
        tags.append("sum")
    basis_checks = 0
    for K in thresholds:
        for bit in (False,True):
            oracle,meta = reversible_oracle(table,K,bit)
            for state in range(N):
                c = QuantumCircuit(oracle.num_qubits)
                for j in range(nq):
                    if state>>j&1:
                        c.x(j)
                c.compose(oracle,inplace=True)
                c.save_statevector()
                good = int(costs[state] <= K)
                target = state+((good << (oracle.num_qubits-1)) if bit else 0)
                circuits.append(c)
                expected.append((target,1.0 if bit else (-1)**good))
                tags.append("bit" if bit else "phase")
                basis_checks += 1
    errors = {k:0.0 for k in ("sum","bit","phase")}
    start = time.perf_counter()
    for first in range(0,len(circuits),16):
        vectors = run(circuits[first:first+16])
        for v,(target,amplitude),tag in zip(vectors,expected[first:first+16],tags[first:first+16]):
            v[target] -= amplitude
            errors[tag] = max(errors[tag],float(np.linalg.norm(v)))
    assert max(errors.values()) < 1e-8, errors
    amplification=[]
    for K in thresholds:
        alpha = float(np.mean(costs<=K))
        if not 0 < alpha < 1:
            continue
        for k in range(4):
            c,meta = grover(table,K,k)
            c.save_statevector()
            v=run([c])[0]
            good = np.flatnonzero(costs<=K)
            observed = float(np.sum(np.abs(v[good])**2))
            ideal = float(np.sin((2*k+1)*np.arcsin(np.sqrt(alpha)))**2)
            leakage = float(np.sum(np.abs(v[N:])**2))
            assert abs(observed-ideal)<1e-8 and leakage<1e-8
            amplification.append(dict(K=K,k=k,alpha=alpha,observed=observed,ideal=ideal,workspace_leakage=leakage))
    return dict(case=name,N=N,thresholds=thresholds,sum_basis_checks=N,bit_phase_basis_checks=basis_checks,
                errors=errors,amplification=amplification,wall_seconds=time.perf_counter()-start,resources=meta)


if __name__ == "__main__":
    folder=ROOT/"results/quantum"
    folder.mkdir(parents=True,exist_ok=True)
    for name in ("B3-C2","B3-C4"):
        file=folder/f"verification_{name}.json"
        if file.exists():
            print(name,"verified result reused",flush=True)
            continue
        table=json.loads((ROOT/f"results/model/{name}.json").read_text())
        report=verify(table,name)
        file.write_text(json.dumps(report,indent=2),encoding="utf-8")
        print(name,report["errors"],report["wall_seconds"],flush=True)
