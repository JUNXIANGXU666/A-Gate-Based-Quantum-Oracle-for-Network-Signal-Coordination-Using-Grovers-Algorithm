"""Validate and execute small full oracles at documented cost resolutions."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy, transpile
from qiskit_aer import AerSimulator
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

from quantum_oracle import grover, reduction, register_costs
from verify_quantum import verify

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"results/hardware_precision"
OUT.mkdir(parents=True,exist_ok=True)


def save(name, data):
    (OUT/name).write_text(json.dumps(data,indent=2,default=str),encoding="utf8")


def prepare():
    if (OUT/"preparation_complete.json").exists():
        print("Existing validated preparation retained.")
        return
    tables = []
    for folder, name, eta in [("model","B3-C2",64),("resco","RC3-C2",8)]:
        original = json.loads((ROOT/f"results/{folder}/{name}.json").read_text())
        table = copy.deepcopy(original)
        table.pop("exact",None)
        table["scenario"]["quantum_unit"] = eta
        table["integer"] = np.floor(np.array(table["continuous"])/eta+.5).astype(int).tolist()
        costs, _ = register_costs(table)
        fine, _ = register_costs(original)
        assert np.array_equal(costs==costs.min(),fine==fine.min())
        assert np.mean(costs==costs.min()) == .25
        report = verify(table,f"{name}-eta{eta}")
        save(f"verification_{name}.json",report)
        save(f"table_{name}.json",table)
        tables.append((name,table,dict(eta=eta,sum_qubits=reduction(table)[3],
                       same_minimum_marked_set_as_fine=True,
                       worst_case_optimisation_loss_bound=len(table["links"])*eta,
                       fine_source_sha256=hashlib.sha256((ROOT/f"results/{folder}/{name}.json").read_bytes()).hexdigest())))
    service = QiskitRuntimeService()
    backend = service.backend("ibm_fez")
    usage = service.usage()
    save("initial_usage.json",usage)
    print("Remaining free seconds:",usage.get("usage_remaining_seconds"),flush=True)
    circuits, rows, validations = [], [], []
    simulator = AerSimulator(method="statevector",max_parallel_threads=4)
    for seed in (11,29,47):
        for name,table,precision in tables:
            costs, _ = register_costs(table)
            K = int(costs.min())
            logical, meta = grover(table,K,1,measurement=True)
            manager = generate_preset_pass_manager(backend=backend,optimization_level=3,seed_transpiler=seed)
            amplified = manager.run(logical)
            placement = amplified.layout.initial_index_layout(filter_ancillas=True)
            baseline, _ = grover(table,K,0,measurement=True)
            zero = generate_preset_pass_manager(backend=backend,optimization_level=3,seed_transpiler=seed,
                                                initial_layout=placement).run(baseline)
            for k, circuit in enumerate((zero,amplified)):
                used = sorted({circuit.find_bit(q).index for instruction in circuit.data for q in instruction.qubits})
                mapping = {old:i for i,old in enumerate(used)}
                measured = {circuit.find_bit(v.clbits[0]).index:circuit.find_bit(v.qubits[0]).index
                            for v in circuit.data if v.operation.name=="measure"}
                compact = QuantumCircuit(len(used))
                compact.global_phase = circuit.global_phase
                for instruction in circuit.data:
                    if instruction.operation.name not in ("measure","barrier"):
                        compact.append(instruction.operation,[mapping[circuit.find_bit(q).index] for q in instruction.qubits])
                compact.save_probabilities_dict([mapping[measured[j]] for j in range(len(measured))])
                result = simulator.run(transpile(compact,simulator,optimization_level=0)).result()
                assert result.success
                probabilities = result.data(0)["probabilities"]
                success = sum(v for state,v in probabilities.items()
                              if costs[int(state,16) if isinstance(state,str) else state] <= K)
                ideal = .25 if k==0 else 1.0
                assert abs(success-ideal)<1e-8
                validations.append(dict(case=name,seed=seed,k=k,error=abs(success-ideal)))
                row = dict(case=name,route="reversible",k=k,K=K,alpha=.25,ideal=ideal,seed_transpiler=seed,
                           shots=4096,logical_qubits=logical.num_qubits,offset_qubits=meta["offset_qubits"],
                           active_physical_qubits=used,initial_layout=placement,
                           final_layout=circuit.layout.final_index_layout(filter_ancillas=True),
                           depth=circuit.depth(),operations=dict(circuit.count_ops()),
                           two_qubit_gates=sum(n for gate,n in circuit.count_ops().items() if gate in ("cx","cz","ecr")),
                           estimated_circuit_seconds=circuit.estimate_duration(backend.target,unit="s"),**precision)
                circuits.append(circuit)
                rows.append(row)
                print(name,"eta",precision["eta"],"seed",seed,"k",k,"2Q",row["two_qubit_gates"],flush=True)
    with (OUT/"circuits.qpy").open("wb") as f:
        qpy.dump(circuits,f)
    save("circuits.json",rows)
    save("isa_verification.json",validations)
    save("preparation_complete.json",dict(circuits=len(rows),basis_tests=56,all_isa_circuits_verified=True,
         qpy_sha256=hashlib.sha256((OUT/"circuits.qpy").read_bytes()).hexdigest(),
         design="Two full oracles, three transpiler seeds, k=0/1, two execution batches of 4096 shots. No mitigation."))


def execute():
    certificate = json.loads((OUT/"preparation_complete.json").read_text())
    assert certificate["all_isa_circuits_verified"]
    assert certificate["qpy_sha256"] == hashlib.sha256((OUT/"circuits.qpy").read_bytes()).hexdigest()
    rows = json.loads((OUT/"circuits.json").read_text())
    prior = sum(v["actual_quantum_seconds"] for v in json.loads((ROOT/"results/hardware/job_ledger.json").read_text()))
    service = QiskitRuntimeService()
    backend = service.backend("ibm_fez")
    ledger = []
    for repeat in (1,2):
        record_file = OUT/f"job_{repeat}.json"
        counts_file = OUT/f"counts_{repeat}.json"
        if counts_file.exists():
            ledger.append(json.loads(record_file.read_text()))
            continue
        if record_file.exists():
            record = json.loads(record_file.read_text())
            job = service.job(record["job_id"])
        else:
            usage = service.usage()
            assert usage["plan_id"] == json.loads((OUT/"initial_usage.json").read_text())["plan_id"]
            remaining = float(usage["usage_remaining_seconds"])
            rep_delay = backend.configuration().default_rep_delay
            reset = backend.target["reset"][(0,)].duration or 0
            estimate = sum((v["estimated_circuit_seconds"]+rep_delay+reset)*4096+2 for v in rows)
            limit = math.ceil(estimate*1.15+4)
            consumed = prior+sum(v["actual_quantum_seconds"] for v in ledger)
            assert consumed+limit<=600 and remaining-limit>=10,(consumed,remaining,limit)
            options = dict(max_execution_time=limit,default_shots=4096,
                           dynamical_decoupling={"enable":False},twirling={"enable_gates":False,"enable_measure":False},
                           execution={"init_qubits":True,"rep_delay":rep_delay})
            with (OUT/"circuits.qpy").open("rb") as f:
                circuits = qpy.load(f)
            job = SamplerV2(mode=backend,options=options).run(circuits,shots=4096)
            record = dict(job_id=job.job_id(),repeat=repeat,backend=backend.name,options=options,
                          status="submitted",estimated_quantum_seconds=estimate,limit_seconds=limit,
                          usage_before=usage,properties_before=backend.properties().to_dict(),
                          qpy_sha256=certificate["qpy_sha256"])
            save(record_file.name,record)
            print("Submitted precision batch",repeat,job.job_id(),"cap",limit,flush=True)
        results = job.result()
        counts = []
        for row,pub in zip(rows,results):
            measured = pub.data.offset.get_counts()
            assert sum(measured.values())==4096
            counts.append({**row,"repeat":repeat,"counts":measured,"job_id":job.job_id(),"pub_metadata":pub.metadata})
        save(counts_file.name,counts)
        metrics = job.metrics()
        record.update(status=str(job.status()),metrics=metrics,actual_quantum_seconds=float(metrics["usage"]["quantum_seconds"]),
                      usage_after=service.usage())
        save(record_file.name,record)
        ledger.append(record)
        save("job_ledger.json",ledger)
        print("Completed precision batch",repeat,"actual seconds",record["actual_quantum_seconds"],flush=True)
    print("Cumulative project QPU seconds",prior+sum(v["actual_quantum_seconds"] for v in ledger),flush=True)


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--execute",action="store_true",help="Authorise actual IBM execution within the free quota")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    if args.execute:
        execute()
