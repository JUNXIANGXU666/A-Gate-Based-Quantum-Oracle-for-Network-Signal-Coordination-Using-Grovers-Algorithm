"""Finite offset tables from deterministic fluid queues, in vehicle-seconds."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import product
import json
from pathlib import Path
import time

import numpy as np


@dataclass
class Scenario:
    name: str
    n: int
    family: str
    states: int = 8
    cycle: int = 60
    load: float = 1.0
    saturation: float = 0.5
    quantum_unit: float = 1.0

    @property
    def greens(self):
        return [32, 36, 30, 34, 32, 34, 36, 30][:self.n]

    def routes(self):
        forward = list(range(self.n))
        if self.family == "ring":
            return [(forward + [0], 0.18*self.load, "forward"),
                    ([0] + list(range(self.n-1, -1, -1)), 0.13*self.load, "reverse")]
        routes = [(forward, 0.18*self.load, "forward")]
        if self.family == "bidirectional":
            routes.append((forward[::-1], 0.13*self.load, "reverse"))
        return routes

    def links(self):
        result = []
        for route, flow, direction in self.routes():
            for i, j in zip(route, route[1:]):
                travel = 11 + ((3*i + 5*j) % 13)
                result.append(dict(i=i, j=j, flow=flow, travel=travel, direction=direction))
        return result


def queue_step(arrival: float, service: float, queue: float):
    discharge = min(queue + arrival, service)
    return queue + arrival - discharge, discharge


def release_profile(flow, green, cycle=60, saturation=0.5, cycles=40):
    queue = 0.0
    last = []
    for t in range(cycle*cycles):
        queue, discharge = queue_step(flow, saturation*(t % cycle < green), queue)
        if t >= cycle*(cycles-1):
            last.append(discharge)
    return np.asarray(last)


def link_delay(scenario, link, difference, return_trace=False):
    T = scenario.cycle
    profile = release_profile(link["flow"], scenario.greens[link["i"]], T, scenario.saturation)
    # Fractional offset shifts use conservative periodic linear interpolation.
    shift = link["travel"] + difference*T/scenario.states
    indices = (np.arange(T)-shift) % T
    a0 = np.floor(indices).astype(int)
    fraction = indices-a0
    arrivals = profile[a0]*(1-fraction) + profile[(a0+1) % T]*fraction
    queue, total = 0.0, 0.0
    trace = []
    for t in range(40*T):
        queue, _ = queue_step(arrivals[t % T], scenario.saturation*(t % T < scenario.greens[link["j"]]), queue)
        if t >= 20*T:
            total += queue
        if t >= 39*T:
            trace.append(queue)
    delay = total/20
    if return_trace:
        return delay, arrivals, np.asarray(trace)
    return delay


def build_tables(scenario):
    started = time.perf_counter()
    links = scenario.links()
    continuous = np.array([[link_delay(scenario, edge, d) for d in range(scenario.states)] for edge in links])
    integers = np.floor(continuous/scenario.quantum_unit + 0.5).astype(np.int64)
    return {"scenario": asdict(scenario), "greens": scenario.greens, "links": links,
            "continuous": continuous.tolist(), "integer": integers.tolist(),
            "construction_seconds": time.perf_counter()-started}


def assignments(scenario):
    return np.column_stack((np.zeros(scenario.states**(scenario.n-1), dtype=np.int16),
                            np.array(list(product(range(scenario.states), repeat=scenario.n-1)), dtype=np.int16)))


def evaluate(table, offsets, integer=True):
    a = np.asarray(offsets)
    values = np.array(table["integer" if integer else "continuous"])
    C = table["scenario"]["states"]
    result = np.zeros(a.shape[:-1], dtype=values.dtype)
    for e, edge in enumerate(table["links"]):
        result += values[e, (a[..., edge["i"]]-a[..., edge["j"]]) % C]
    return result


def enumerate_case(table):
    scenario = Scenario(**table["scenario"])
    started = time.perf_counter()
    offsets = assignments(scenario)
    costs = evaluate(table, offsets)
    continuous = evaluate(table, offsets, False)
    best = int(np.argmin(costs))
    return {"N": len(costs), "minimum": int(costs[best]), "best_offsets": offsets[best].tolist(),
            "continuous_at_best": float(continuous[best]), "continuous_minimum": float(continuous.min()),
            "minimum_count": int((costs == costs[best]).sum()), "uniform_cost": int(costs[0]),
            "independent_link_minima_sum": int(np.array(table["integer"]).min(axis=1).sum()),
            "conflict_gap": int(costs.min()-np.array(table["integer"]).min(axis=1).sum()),
            "enumeration_seconds": time.perf_counter()-started}, offsets, costs


def main():
    root = Path(__file__).resolve().parents[1]
    out = root/"results/model"
    out.mkdir(parents=True, exist_ok=True)
    reports = {}
    cases = [Scenario(f"{name}-{load:g}", 4, family, load=load)
             for name, family in [("U4", "unidirectional"), ("B4", "bidirectional"), ("R4", "ring")]
             for load in [0.65, 1.0, 1.35, 1.55]]
    cases += [Scenario(f"B{n}-C{c}", n, "bidirectional", states=c) for n, c in [(3, 2), (3, 4), (4, 4), (5, 4), (6, 4), (8, 4), (6, 8)]]
    for scenario in cases:
        table = build_tables(scenario)
        report, offsets, costs = enumerate_case(table)
        (out/f"{scenario.name}.json").write_text(json.dumps({**table, "exact": report}, indent=2), encoding="utf-8")
        np.savez_compressed(out/f"{scenario.name}.npz", offsets=offsets, costs=costs)
        reports[scenario.name] = report
        print(scenario.name, report, flush=True)
    (out/"summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
