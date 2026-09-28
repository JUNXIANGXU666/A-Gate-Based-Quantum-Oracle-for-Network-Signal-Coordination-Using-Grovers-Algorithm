"""Add the binary test and genuine RESCO cases without rerunning frozen comparisons."""
import json
from pathlib import Path
import time
import numpy as np

from optimisation_experiments import adaptive_quantum_reference, classical, exact_path_or_ring
from quantum_oracle import register_costs

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/"results/optimisation_extended"
    out.mkdir(parents=True,exist_ok=True)
    records = []
    for folder,name in [("model","B3-C2"),("resco","RC3-C2"),("resco","RC3-C4"),("resco","RC3-1")]:
        target = out/f"{name}.json"
        if target.exists():
            records.append(json.loads(target.read_text()))
            continue
        table = json.loads((ROOT/f"results/{folder}/{name}.json").read_text())
        costs,offsets = register_costs(table)
        timings = []
        for _ in range(20):
            start = time.perf_counter()
            minimum,x = exact_path_or_ring(table)
            timings.append(time.perf_counter()-start)
        assert minimum == int(costs.min())
        budget = max(16,int(8*np.ceil(np.sqrt(len(costs)))))
        runs = {method:[] for method in ("random","coordinate","quantum_reference")}
        for seed in range(100):
            for method in ("random","coordinate"):
                runs[method].append(classical(table,costs,offsets,budget,seed,method))
            runs["quantum_reference"].append(adaptive_quantum_reference(costs,budget,seed))
        row = dict(case=name,N=len(costs),query_budget=budget,minimum=minimum,dp_offsets=x,
                   dp_seconds_median=float(np.median(timings)),runs=runs)
        target.write_text(json.dumps(row),encoding="utf8")
        records.append(row)
        print(name,{k:sum(r["best"]==minimum for r in v) for k,v in runs.items()},flush=True)
    frozen = json.loads((ROOT/"results/optimisation/all_results.json").read_text())
    (out/"all_results.json").write_text(json.dumps(records),encoding="utf8")
    (out/"combined_results.json").write_text(json.dumps(frozen+records),encoding="utf8")
    print("Compared",len(frozen+records),"instances.")


if __name__ == "__main__":
    main()
