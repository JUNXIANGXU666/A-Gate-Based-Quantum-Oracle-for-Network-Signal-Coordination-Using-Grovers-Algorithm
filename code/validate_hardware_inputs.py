import json
from pathlib import Path
import numpy as np
from qiskit import QuantumCircuit, qpy, transpile
from qiskit_aer import AerSimulator
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from quantum_oracle import grover, register_costs

root=Path(__file__).resolve().parents[1]
folder=root/"results/hardware"
backend=QiskitRuntimeService().backend("ibm_fez")
sim=AerSimulator(method="statevector",max_parallel_threads=4)
audit=[]
for seed in (11,29,47):
    rows=json.loads((folder/f"seed_{seed}.json").read_text())
    with (folder/f"seed_{seed}.qpy").open("rb") as f:
        circuits=qpy.load(f)
    for i in range(0,len(rows),2):
        row=rows[i]
        table=json.loads((root/f"results/model/{row['case']}.json").read_text())
        c,meta=grover(table,row["K"],0,row["route"],measurement=True)
        pm=generate_preset_pass_manager(backend=backend,optimization_level=3,seed_transpiler=seed,
                                        initial_layout=circuits[i+1].layout.initial_index_layout(filter_ancillas=True))
        circuits[i]=pm.run(c)
        row.update(layout=circuits[i].layout.final_index_layout(filter_ancillas=True),depth=circuits[i].depth(),operations=dict(circuits[i].count_ops()))
        for j in (i,i+1):
            original=circuits[j]
            used=sorted({original.find_bit(q).index for instruction in original.data for q in instruction.qubits})
            measured={original.find_bit(instruction.clbits[0]).index:original.find_bit(instruction.qubits[0]).index
                      for instruction in original.data if instruction.operation.name=="measure"}
            mapping={old:k for k,old in enumerate(used)}
            compact=QuantumCircuit(len(used))
            compact.global_phase=original.global_phase
            for instruction in original.data:
                if instruction.operation.name not in ("measure","barrier"):
                    compact.append(instruction.operation,[mapping[original.find_bit(q).index] for q in instruction.qubits])
            compact.save_probabilities_dict([mapping[measured[k]] for k in range(len(measured))])
            if seed==11:
                result=sim.run(transpile(compact,sim,optimization_level=0)).result()
                assert result.success
                probs=result.data(0)["probabilities"]
                costs,_=register_costs(table)
                feasible=sum(prob for state,prob in probs.items() if costs[int(state,16) if isinstance(state,str) else state] <= row["K"])
                error=abs(feasible-rows[j]["ideal"])
                assert error<1e-7, (rows[j],error)
                audit.append({"case":row["case"],"route":row["route"],"k":rows[j]["k"],"active_qubits":len(used),"probability_error":error})
                print(audit[-1],flush=True)
            rows[j]["active_physical_qubits"]=used
    with (folder/f"seed_{seed}.qpy").open("wb") as f:
        qpy.dump(circuits,f)
    (folder/f"seed_{seed}.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
(folder/"isa_verification.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
