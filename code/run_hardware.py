"""Budget-guarded IBM job execution with restart-safe job recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from qiskit import qpy
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2


ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"results/hardware"


def save(path, data):
    path.write_text(json.dumps(data,indent=2,default=str),encoding="utf-8")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true",help="Authorise new IBM jobs and QPU consumption")
    if not parser.parse_args().execute:
        parser.error("New hardware execution requires --execute. Archived counts need no IBM connection.")
    assert (FOLDER/"isa_verification.json").exists()
    service=QiskitRuntimeService()
    backend=service.backend("ibm_fez")
    ledger=[]
    for repeat in range(1,6):
        for seed in (11,29,47):
            identity=f"repeat_{repeat}_seed_{seed}"
            record_file=FOLDER/f"job_{identity}.json"
            result_file=FOLDER/f"counts_{identity}.json"
            metadata=json.loads((FOLDER/f"seed_{seed}.json").read_text())
            if result_file.exists():
                ledger.append(json.loads(record_file.read_text()))
                continue
            if record_file.exists():
                record=json.loads(record_file.read_text())
                job=service.job(record["job_id"])
            else:
                usage=service.usage()
                assert usage["plan_id"] == json.loads((FOLDER/"initial_usage.json").read_text())["plan_id"]
                remaining=float(usage["usage_remaining_seconds"])
                consumed=sum(float(r.get("actual_quantum_seconds",0)) for r in ledger)
                rep_delay=backend.configuration().default_rep_delay
                reset=backend.target["reset"][(0,)].duration or 0
                estimate=sum((r["estimated_circuit_seconds"]+rep_delay+reset)*r["shots"]+2 for r in metadata)
                limit=math.ceil(estimate*1.15+4)
                assert consumed+limit <= 540 and remaining-limit >= 60, (consumed,remaining,limit)
                with (FOLDER/f"seed_{seed}.qpy").open("rb") as f:
                    circuits=qpy.load(f)
                options={"max_execution_time":limit,"default_shots":4096,
                         "dynamical_decoupling":{"enable":False},
                         "twirling":{"enable_gates":False,"enable_measure":False},
                         "execution":{"init_qubits":True,"rep_delay":rep_delay}}
                sampler=SamplerV2(mode=backend,options=options)
                job=sampler.run(circuits,shots=4096)
                record={"job_id":job.job_id(),"identity":identity,"repeat":repeat,"seed_transpiler":seed,
                        "backend":backend.name,"usage_before":usage,"options":options,
                        "estimated_quantum_seconds":estimate,"limit_seconds":limit,
                        "qpy_sha256":hashlib.sha256((FOLDER/f"seed_{seed}.qpy").read_bytes()).hexdigest(),
                        "properties_before":backend.properties().to_dict(),"status":"submitted"}
                save(record_file,record)
                print("Submitted",identity,job.job_id(),"estimate",estimate,"cap",limit,flush=True)
            results=job.result()
            rows=[]
            for meta,pub in zip(metadata,results):
                counts=pub.data.offset.get_counts()
                assert sum(counts.values())==meta["shots"]
                rows.append({**meta,"repeat":repeat,"counts":counts,"pub_metadata":pub.metadata,"job_id":job.job_id()})
            save(result_file,rows)
            record.update(status=str(job.status()),metrics=job.metrics(),usage=job.usage(),usage_after=service.usage())
            record["actual_quantum_seconds"]=float(record["metrics"]["usage"]["quantum_seconds"])
            save(record_file,record)
            ledger.append(record)
            save(FOLDER/"job_ledger.json",ledger)
            print("Completed",identity,"quantum seconds",record["actual_quantum_seconds"],flush=True)
    save(FOLDER/"job_ledger.json",ledger)
    print("All planned jobs complete. Total QPU seconds",sum(r["actual_quantum_seconds"] for r in ledger),flush=True)


if __name__=="__main__":
    main()
