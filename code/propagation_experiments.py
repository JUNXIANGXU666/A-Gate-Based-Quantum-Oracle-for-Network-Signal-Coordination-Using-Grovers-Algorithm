"""Propagated-arrival sensitivity and discrete two-direction bandwidth references."""
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from traffic_model import Scenario, assignments, evaluate, queue_step

ROOT = Path(__file__).resolve().parents[1]


def shift_periodic(values, shift):
    indices = (np.arange(len(values))-shift) % len(values)
    lower = np.floor(indices).astype(int)
    fraction = indices-lower
    return values[lower]*(1-fraction) + values[(lower+1) % len(values)]*fraction


def discharge_series(arrivals, green, offset, saturation, cycle):
    departures = np.zeros(len(arrivals))
    queue = 0.0
    for t, arrival in enumerate(arrivals):
        service = saturation * ((t-offset) % cycle < green)
        queue, departures[t] = queue_step(arrival, service, queue)
    assert departures.sum() <= arrivals.sum()+1e-8
    assert abs(arrivals.sum()-departures.sum()-queue) < 1e-7
    return departures


def propagated_profiles(scenario, offsets):
    T = scenario.cycle
    horizon = 80*T
    edges = {(e["i"], e["j"]): e for e in scenario.links()}
    profiles = {}
    for route, flow, _ in scenario.routes():
        arrivals = np.full(horizon, flow)
        for i, j in zip(route, route[1:]):
            offset = offsets[i]*T/scenario.states
            departures = discharge_series(arrivals, scenario.greens[i], offset, scenario.saturation, T)
            profiles[i, j] = shift_periodic(departures[-T:], -offset)
            travel = edges[i, j]["travel"]
            arrivals = np.interp(np.arange(horizon)-travel, np.arange(horizon), departures, left=0, right=0)
    assert set(profiles) == set(edges)
    return profiles


def tables_from_profiles(scenario, profiles):
    T = scenario.cycle
    rows = []
    for edge in scenario.links():
        row = []
        for difference in range(scenario.states):
            arrivals = shift_periodic(profiles[edge["i"], edge["j"]], edge["travel"]+difference*T/scenario.states)
            queue, total = 0.0, 0.0
            for t in range(40*T):
                queue, _ = queue_step(arrivals[t % T], scenario.saturation*(t % T < scenario.greens[edge["j"]]), queue)
                if t >= 20*T:
                    total += queue
            row.append(total/20)
        rows.append(row)
    continuous = np.asarray(rows)
    return dict(scenario=asdict(scenario), greens=scenario.greens, links=scenario.links(),
                continuous=continuous.tolist(), integer=np.floor(continuous/scenario.quantum_unit+.5).astype(int).tolist())


def iterate(frozen, maximum=25):
    scenario = Scenario(**frozen["scenario"])
    domain = assignments(scenario)
    current = list(frozen["exact"]["best_offsets"])
    seen = {tuple(current)}
    history = []
    status = "iteration_limit"
    table = frozen
    for step in range(1, maximum+1):
        profiles = propagated_profiles(scenario, current)
        table = tables_from_profiles(scenario, profiles)
        costs = evaluate(table, domain)
        optimum = int(costs.min())
        incumbent = int(evaluate(table, current))
        candidate = current if incumbent == optimum else domain[int(costs.argmin())].tolist()
        history.append(dict(iteration=step, input_offsets=current, output_offsets=candidate,
                            incumbent_cost=incumbent, minimum=optimum,
                            conflict_gap=int(optimum-np.asarray(table["integer"]).min(axis=1).sum()),
                            profiles=[profiles[e["i"], e["j"]].tolist() for e in table["links"]]))
        if candidate == current:
            status = "fixed_point"
            break
        if tuple(candidate) in seen:
            status = "cycle_detected"
            break
        current = list(candidate)
        seen.add(tuple(current))
    return dict(case=scenario.name, status=status, iterations=len(history), offsets=current,
                history=history, final_tables=table,
                stopping_rule="Keep incumbent on ties. Stop on unchanged plan, repeated plan, or 25 rounds. On a cycle retain the last distinct input plan.")


def route_bandwidth(scenario, route, offsets):
    T = scenario.cycle
    edges = {(e["i"],e["j"]):e for e in scenario.links()}
    available = [(0.0,float(T))]
    travel = 0.0
    for k, node in enumerate(route):
        if k:
            travel += edges[route[k-1],node]["travel"]
        start = (offsets[node]*T/scenario.states-travel) % T
        end = start+scenario.greens[node]
        windows = [(start,min(end,T))] + ([(0.0,end-T)] if end > T else [])
        available = [(max(a,c),min(b,d)) for a,b in available for c,d in windows if min(b,d)>max(a,c)+1e-10]
        if not available:
            return 0.0
    available.sort()
    widths = [b-a for a,b in available]
    if len(available)>1 and abs(available[0][0])<1e-8 and abs(available[-1][1]-T)<1e-8:
        widths.append(widths[0]+widths[-1])
    return float(max(widths))


def bandwidth_plan(scenario):
    domain = assignments(scenario)
    routes = scenario.routes()
    best = None
    for x in domain:
        bands = [route_bandwidth(scenario, route, x) for route, _, _ in routes]
        score = sum(band*route[1] for band,route in zip(bands,routes))
        if best is None or score > best[0]+1e-10:
            best = (score, x.tolist(), bands)
    return dict(offsets=best[1], weighted_bandwidth=best[0], directional_bandwidths=best[2],
                domain_size=len(domain), definition="Flow-weighted sum of longest common periodic green intervals along the complete directional routes; exhaustive discrete optimum.")


def progression(scenario):
    x = [0]
    edges = {(e["i"], e["j"]):e for e in scenario.links()}
    for i in range(scenario.n-1):
        x.append((x[-1]+round(edges[i,i+1]["travel"]*scenario.states/scenario.cycle)) % scenario.states)
    return x


def main():
    out = ROOT/"results/traffic_extension"
    out.mkdir(parents=True,exist_ok=True)
    records = []
    for family in ("U4","B4","R4","RC3"):
        for load in (.65,1,1.35,1.55):
            name = f"{family}-{load:g}"
            source = ROOT/("results/resco" if family=="RC3" else "results/model")/f"{name}.json"
            target = out/f"{name}.json"
            if target.exists():
                records.append(json.loads(target.read_text()))
                continue
            frozen = json.loads(source.read_text())
            scenario = Scenario(**frozen["scenario"])
            propagation = iterate(frozen)
            bandwidth = bandwidth_plan(scenario)
            plans = dict(synchronised=[0]*scenario.n, progression=progression(scenario),
                         optimised=frozen["exact"]["best_offsets"], propagated=propagation["offsets"],
                         bandwidth=bandwidth["offsets"])
            costs = {k:int(evaluate(frozen,v)) for k,v in plans.items()}
            record = dict(case=name, scenario=asdict(scenario), plans=plans, frozen_costs=costs,
                          propagation=propagation, bandwidth=bandwidth)
            target.write_text(json.dumps(record,indent=2),encoding="utf8")
            records.append(record)
            print(name, propagation["status"], propagation["iterations"], plans, costs, flush=True)
    (out/"all_plans.json").write_text(json.dumps(records,indent=2),encoding="utf8")


if __name__ == "__main__":
    main()
