from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
from qiskit import qpy
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService

from quantum_oracle import grover, register_costs


ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=ROOT/"results/hardware"
    folder.mkdir(parents=True,exist_ok=True)
    service=QiskitRuntimeService()
    backend=service.backend("ibm_fez")
    configuration=backend.configuration().to_dict()
    properties=backend.properties().to_dict()
    usage=service.usage()
    (folder/"backend_configuration.json").write_text(json.dumps(configuration,indent=2,default=str),encoding="utf-8")
    (folder/"backend_properties.json").write_text(json.dumps(properties,indent=2,default=str),encoding="utf-8")
    (folder/"initial_usage.json").write_text(json.dumps(usage,indent=2,default=str),encoding="utf-8")
    rows=[]
    for seed in (11,29,47):
        manager=generate_preset_pass_manager(backend=backend,optimization_level=3,seed_transpiler=seed)
        circuits=[]
        for name,route in [("B3-C2","reversible"),("B3-C4","reversible"),
                           ("B3-C4","compiled"),("B4-C4","compiled"),("B5-C4","compiled"),("B6-C4","compiled")]:
            table=json.loads((ROOT/f"results/model/{name}.json").read_text())
            costs,_=register_costs(table)
            K=int(np.sort(costs)[max(0,len(costs)//8-1)])
            alpha=float(np.mean(costs<=K))
            for k in (0,1):
                circuit,meta=grover(table,K,k,route,measurement=True)
                start=time.perf_counter()
                isa=manager.run(circuit)
                two=sum(count for gate,count in isa.count_ops().items() if gate in ("cx","cz","ecr"))
                duration=isa.estimate_duration(backend.target,unit="s")
                row=dict(case=name,route=route,seed_transpiler=seed,k=k,K=K,alpha=alpha,
                         ideal=float(np.sin((2*k+1)*np.arcsin(np.sqrt(alpha)))**2),
                         logical_qubits=circuit.num_qubits,offset_qubits=meta["offset_qubits"],
                         logical_operations=dict(circuit.count_ops()),depth=isa.depth(),two_qubit_gates=int(two),
                         operations=dict(isa.count_ops()),estimated_circuit_seconds=duration,
                         compilation_seconds=time.perf_counter()-start,
                         layout=isa.layout.final_index_layout(filter_ancillas=True),index=len(circuits),shots=4096)
                rows.append(row)
                circuits.append(isa)
                print(seed,name,route,k,"2q",two,"seconds",duration,flush=True)
        with (folder/f"seed_{seed}.qpy").open("wb") as f:
            qpy.dump(circuits,f)
        (folder/f"seed_{seed}.json").write_text(json.dumps([r for r in rows if r["seed_transpiler"]==seed],indent=2),encoding="utf-8")
    (folder/"preparation.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
    print("Estimated circuit execution seconds",sum((r["estimated_circuit_seconds"]+backend.configuration().default_rep_delay)*r["shots"] for r in rows),flush=True)


if __name__=="__main__":
    main()
