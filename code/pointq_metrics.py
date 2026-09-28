from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def analyse(certificate, manifest, warmup=1200, end=4800):
    cert = json.loads(Path(certificate).read_text(encoding="utf-8"))
    network = json.loads(Path(manifest).read_text(encoding="utf-8"))
    phases = {(m["a"],m["b"]):0 for m in network["movements"]}
    queues = phases.copy()
    path_by_entry = {p["links"][0]:p for p in network["paths"]}
    travel_by_link = {row[0]:row[5] for row in network["links"]}
    arrivals, exits, completed_delays = [], {}, []
    last, integral, peak, end_count = 0.0, 0.0, 0, 0
    series, signals = [], []
    with open(cert["event_file"], newline="", encoding="utf-8") as source:
        for row in csv.reader(source):
            t, event = float(row[0]), int(row[1])
            assert t >= last-1e-8, "PointQ events are not ordered"
            integral += sum(queues.values())*max(0, min(t,end)-max(last,warmup))
            last = t
            if event == 1:
                arrivals.append((int(row[13]), float(row[12])))
            if event in (1,4,5):
                phase = tuple(ast.literal_eval(row[18]))
                q = ast.literal_eval(row[29])
                assert phase in phases and isinstance(q,list)
                queues[phase] = len(q)
                if t >= warmup:
                    peak = max(peak,sum(queues.values()))
                    series.append((t,sum(queues.values())))
            if event == 4 and float(row[23]) >= 0:
                vehicle = int(row[11])
                assert vehicle not in exits, "A vehicle exits twice"
                exits[vehicle] = float(row[23])
                if warmup <= float(row[12]) and float(row[23]) <= end:
                    path = path_by_entry[int(row[13])]
                    free = sum(travel_by_link[l] for l in path["links"])
                    completed_delays.append(float(row[23])-float(row[12])-free)
            if event == 3 and t >= warmup and t < warmup+120:
                signals.append([t,row[2],row[43]])
    integral += sum(queues.values())*max(0,end-max(last,warmup))
    inflow = sum(warmup <= t < end for _,t in arrivals)
    outflow = sum(warmup <= t < end for t in exits.values())
    assert len(arrivals) >= len(exits)
    assert sum(queues.values()) <= len(arrivals)-len(exits)
    arrivals.sort()
    arrival_hash = hashlib.sha256(json.dumps(arrivals).encode()).hexdigest()
    bins = np.arange(warmup,end+1,30)
    a = np.asarray(series)
    sampled = a[np.clip(np.searchsorted(a[:,0],bins,side="right")-1,0,len(a)-1),1]
    result = {"run_id":cert["run_id"],"warmup":warmup,"end":end,"arrivals":inflow,"departures":outflow,
              "all_arrivals":len(arrivals),"all_exits":len(exits),"arrival_hash":arrival_hash,
              "queue_integral_vehicle_seconds":integral,"mean_network_queue":integral/(end-warmup),
              "queue_time_per_entering_vehicle":integral/inflow,"peak_network_queue":peak,
              "ending_queue":sum(queues.values()),"unfinished_vehicles":len(arrivals)-len(exits),
              "completed_mean_delay":float(np.mean(completed_delays)),"completed_cohort":len(completed_delays),
              "throughput_vehicles_hour":outflow/(end-warmup)*3600,
              "time_series":{"seconds":bins.tolist(),"queue":sampled.tolist()},"signal_sample":signals}
    return result
