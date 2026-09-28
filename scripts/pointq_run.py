from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import shutil
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "vendor/pointq/sim_1/cc"


def short_path(path: Path) -> str:
    if os.name != "nt":
        return str(path.resolve())
    buffer = ctypes.create_unicode_buffer(32768)
    size = ctypes.windll.kernel32.GetShortPathNameW(str(path.resolve()), buffer, len(buffer))
    return buffer.value if size else str(path.resolve())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seconds", type=int, default=7200)
    parser.add_argument("--seed", type=int, default=37)
    parser.add_argument("--network", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--settings", type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    folder = ROOT / "pq" / args.run_id
    certificate = folder / "completed.json"
    if certificate.exists():
        print(certificate.read_text(encoding="utf-8"))
        return
    folder.mkdir(parents=True, exist_ok=True)
    control = args.control.resolve() if args.control else ENGINE / "Control_Param_Files"
    local_control = folder / "Control_Param_Files"
    local_control.mkdir(exist_ok=True)
    for file in control.glob("*.txt"):
        shutil.copy2(file, local_control / file.name)
    for file in [ENGINE/name for name in ("Dsu_1.py", "Creation_parameters_event_treatment.py", "f_d.txt")]:
        shutil.copy2(file, folder / file.name)
    os.chdir(short_path(folder))
    work = Path.cwd()
    sys.path[:0] = [str(work), str(ENGINE)]
    import Dsu_1
    import numpy as np
    network = args.network.resolve() if args.network else ROOT / "vendor/pointq/SMALL_NETWS/sanpablo"
    overrides = {"print_messages_on_terminal": 0, "t_simulation_duration": args.seconds,
                 "val_name_folder_network_files": os.path.relpath(short_path(network), short_path(work.parent)).replace("\\", "/")}
    if args.settings:
        overrides.update(json.loads(args.settings.read_text(encoding="utf-8")))
    for key, value in overrides.items():
        setattr(Dsu_1, key, value)
    random.seed(args.seed)
    np.random.seed(args.seed)
    if overrides.get("val_indicating_stoch_demand") == 1:
        import Cl_Creation_Network
        original = Cl_Creation_Network.Creation_Network.function_creation_network
        def create_network(self, *a, **kw):
            network_object = original(self, *a, **kw)
            for entry_id, entry in network_object.get_di_entry_links_to_network().items():
                rng = random.Random(args.seed*100000+entry_id)
                entry.set_fct_creating_demand_entry_link(rng.expovariate)
            return network_object
        Cl_Creation_Network.Creation_Network.function_creation_network = create_network
    (work / "effective_settings.json").write_text(json.dumps({"seed": args.seed, **overrides}, indent=2), encoding="utf-8")
    started = time.perf_counter()
    with (work / "engine.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            runpy.run_path(str(ENGINE / "Simulation.py"), run_name="__main__")
    events = list(work.glob("Series*/FRes*/file_recording_event_db.txt"))
    if len(events) != 1:
        raise RuntimeError(f"Expected one completed event file, found {len(events)}")
    with events[0].open("rb") as source:
        event_hash = hashlib.file_digest(source, "sha256").hexdigest()
    report = {"run_id": args.run_id, "engine_commit": "769af12f47da7bbfe29570fd6c9da479e10381cb",
              "seed": args.seed, "simulated_seconds": args.seconds,
              "wall_seconds": time.perf_counter()-started,
              "event_file": str(events[0]), "event_bytes": events[0].stat().st_size,
              "event_sha256": event_hash, "status": "completed",
              "demand_streams": "independent per-entry Poisson streams seeded by seed*100000+entry_id"}
    certificate.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
