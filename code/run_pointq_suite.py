from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from pointq_inputs import generate
from pointq_metrics import analyse
from traffic_model import Scenario


ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/"results/pointq_v2"
    out.mkdir(parents=True, exist_ok=True)
    completed = []
    hashes = {}
    for name in ("U4", "B4", "R4"):
        for load in (0.65,1.0,1.35,1.55):
            case = f"{name}-{load:g}"
            table = json.loads((ROOT/f"results/model/{case}.json").read_text())
            scenario = Scenario(**table["scenario"])
            progress = [0]
            for i,j in zip(range(3),range(1,4)):
                travel = next(v["travel"] for v in table["links"] if v["i"]==i and v["j"]==j)
                progress.append((progress[-1]+round(travel*scenario.states/scenario.cycle)) % scenario.states)
            plans = {"synchronised":[0]*4, "progression":progress, "optimised":table["exact"]["best_offsets"]}
            for plan, offsets in plans.items():
                config = ROOT/"configs/pointq_v2"/case/plan
                network, control, settings = generate(scenario,offsets,config)
                for seed in range(101,109):
                    run_id = f"v2_{case}_{plan[:3]}_{seed}"
                    result_file = out/f"{run_id}.json"
                    certificate = ROOT/"pq"/run_id/"completed.json"
                    if not result_file.exists():
                        command = [sys.executable,"-B",str(ROOT/"scripts/pointq_run.py"),"--run-id",run_id,
                                   "--seconds","4800","--seed",str(seed),"--network",str(network),"--control",str(control),"--settings",str(settings)]
                        process = subprocess.run(command, capture_output=True, text=True,encoding="utf-8",errors="replace")
                        if process.returncode:
                            raise RuntimeError(process.stdout+process.stderr)
                        result = analyse(certificate,config/"network_manifest.json")
                        result.update(case=case,plan=plan,seed=seed,offsets=offsets)
                        result_file.write_text(json.dumps(result,indent=2),encoding="utf-8")
                    result = json.loads(result_file.read_text())
                    key = case,seed
                    assert hashes.setdefault(key,result["arrival_hash"]) == result["arrival_hash"], "Unpaired external demand"
                    completed.append(result)
                print(case,plan,"finished",len(completed),flush=True)
    (out/"all_results.json").write_text(json.dumps(completed,indent=2),encoding="utf-8")
    print("Completed",len(completed),"PointQ runs",flush=True)


if __name__ == "__main__":
    main()
