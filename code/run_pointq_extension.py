"""Run paired supplementary plans and the RESCO corridor with upstream PointQ."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from pointq_inputs import generate
from pointq_metrics import analyse
from traffic_model import Scenario

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT/"results/pointq_extended"
    out.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((ROOT/"results/pointq_v2/all_results.json").read_text())
    arrival_hashes = {(r["case"],r["seed"]):r["arrival_hash"] for r in frozen}
    plans_file = ROOT/"results/traffic_extension/all_plans.json"
    all_plans = json.loads(plans_file.read_text())
    matrix = [(record, plan, seed) for record in all_plans
              for plan in (record["plans"] if record["case"].startswith("RC3") else ("propagated","bandwidth"))
              for seed in range(101,109)]
    assert len(matrix) == 352
    completed = []
    for record, plan, seed in matrix:
        case = record["case"]
        offsets = record["plans"][plan]
        scenario = Scenario(**record["scenario"])
        run_id = f"ext_{case}_{plan[:4]}_{seed}"
        target = out/f"{run_id}.json"
        config = ROOT/"configs/pointq_extended"/case/plan
        if not target.exists():
            network,control,settings = generate(scenario,offsets,config)
            command = [sys.executable,"-B",str(ROOT/"scripts/pointq_run.py"),"--run-id",run_id,
                       "--seconds","4800","--seed",str(seed),"--network",str(network),
                       "--control",str(control),"--settings",str(settings)]
            process = subprocess.run(command,capture_output=True,text=True,encoding="utf8",errors="replace")
            if process.returncode:
                raise RuntimeError(process.stdout+process.stderr)
            result = analyse(ROOT/"pq"/run_id/"completed.json",config/"network_manifest.json")
            result.update(case=case,plan=plan,seed=seed,offsets=offsets)
            target.write_text(json.dumps(result,indent=2),encoding="utf8")
        result = json.loads(target.read_text())
        assert result["offsets"] == offsets
        key = case,seed
        assert arrival_hashes.setdefault(key,result["arrival_hash"]) == result["arrival_hash"], key
        completed.append(result)
        checkpoint = dict(planned=len(matrix),completed=len(completed),last=run_id,
                          plans_sha256=hashlib.sha256(plans_file.read_bytes()).hexdigest())
        (out/"checkpoint.json").write_text(json.dumps(checkpoint,indent=2),encoding="utf8")
        if seed == 108:
            print(case,plan,"completed",len(completed),"of",len(matrix),flush=True)
    (out/"all_results.json").write_text(json.dumps(completed,indent=2),encoding="utf8")
    (out/"combined_results.json").write_text(json.dumps(frozen+completed,indent=2),encoding="utf8")
    print("Complete:",len(completed),"new runs;",len(frozen+completed),"total",flush=True)


if __name__ == "__main__":
    main()
