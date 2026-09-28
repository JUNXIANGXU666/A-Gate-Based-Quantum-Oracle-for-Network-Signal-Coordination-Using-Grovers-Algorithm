"""Extract a traceable three-signal corridor from the pinned RESCO Cologne case."""
from collections import Counter, defaultdict
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

from traffic_model import Scenario, build_tables, enumerate_case

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f1ed9a174f8de41fc9d8689373b836bc882570dc"
SOURCE = ROOT / "vendor/RESCO/resco_benchmark/environments/cologne3"
SOURCE_HASHES = {
    'cologne3.net.xml':'9686e5f8a9003e997a39cfef9b13bf474048c497ae249458442f0959738eac69',
    'cologne3.rou.xml':'c9b19210fde78db11e8af163c842a150ad4662cc6370329222bf40706b3913fc',
}


def extract():
    for name,digest in SOURCE_HASHES.items():
        assert hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()==digest,name
    net = ET.parse(SOURCE / "cologne3.net.xml").getroot()
    demand = ET.parse(SOURCE / "cologne3.rou.xml").getroot()
    nodes = sorted([v for v in net.findall("junction") if v.get("type") == "traffic_light"],
                   key=lambda v: float(v.get("x")))
    ids = [v.get("id") for v in nodes]
    assert len(ids) == 3
    edges = {v.get("id"): v for v in net.findall("edge") if v.get("function") != "internal"}
    xmin,xmax=min(float(v.get('x')) for v in nodes)-90,max(float(v.get('x')) for v in nodes)+90
    ymin,ymax=min(float(v.get('y')) for v in nodes)-80,max(float(v.get('y')) for v in nodes)+80
    geometry=[]
    for identifier,edge in edges.items():
        lane=edge.find('lane')
        if lane is None or not lane.get('shape'):
            continue
        shape=[[float(x) for x in pair.split(',')] for pair in lane.get('shape').split()]
        xy=np.array(shape)
        if xy[:,0].max()>=xmin and xy[:,0].min()<=xmax and xy[:,1].max()>=ymin and xy[:,1].min()<=ymax:
            geometry.append(dict(edge=identifier,shape=shape))
    signals = {v.get("id"): v for v in net.findall("tlLogic")}
    connection = defaultdict(list)
    for v in net.findall("connection"):
        if v.get("tl") in ids:
            connection[(v.get("tl"), v.get("from"), v.get("to"))].append(int(v.get("linkIndex")))
    vehicles = demand.findall("vehicle")
    departures = [float(v.get("depart")) for v in vehicles]
    duration = max(departures) - min(departures)
    counts, through = Counter(), Counter()
    paths = defaultdict(Counter)
    movements = defaultdict(Counter)
    for vehicle in vehicles:
        route = vehicle.find("route").get("edges").split()
        visits = [(k, ids.index(edges[e].get("to"))) for k, e in enumerate(route)
                  if e in edges and edges[e].get("to") in ids]
        sequence = tuple(node for _, node in visits)
        for node in set(sequence):
            counts[node] += 1
        if sequence not in ((0, 1, 2), (2, 1, 0)):
            continue
        through[sequence] += 1
        for (a, i), (b, j) in zip(visits, visits[1:]):
            paths[i, j][tuple(route[a+1:b+1])] += 1
        for k, node in visits:
            if k+1 < len(route):
                movements[node][(route[k], route[k+1])] += 1
    assert all(through[r] > 0 for r in ((0, 1, 2), (2, 1, 0)))
    rates = {"forward": through[0, 1, 2] / duration, "reverse": through[2, 1, 0] / duration}
    links = []
    mappings = []
    for (i, j), alternatives in sorted(paths.items()):
        route = alternatives.most_common(1)[0][0]
        segments = []
        for edge in route:
            lanes = edges[edge].findall("lane")
            times = [float(v.get("length"))/float(v.get("speed")) for v in lanes]
            segments.append({"edge": edge, "free_flow_seconds": float(np.mean(times))})
        travel = sum(v["free_flow_seconds"] for v in segments)
        direction = "forward" if i < j else "reverse"
        links.append(dict(i=i, j=j, flow=rates[direction], travel=round(travel, 1), direction=direction))
        mappings.append(dict(i=i, j=j, segments=segments, travel_seconds=travel,
                             selected_route_count=alternatives[route], all_through_count=sum(alternatives.values())))
    greens, green_records = [], []
    for node, identifier in enumerate(ids):
        phases = signals[identifier].findall("phase")
        cycle = sum(float(v.get("duration")) for v in phases)
        fractions = []
        for (incoming, outgoing), count in movements[node].items():
            indices = connection[identifier, incoming, outgoing]
            assert indices
            green = sum(float(v.get("duration")) for v in phases
                        if any(v.get("state")[k] in "Gg" for k in indices))
            fractions.append((green/cycle, count))
        fraction = sum(x*w for x, w in fractions) / sum(w for _, w in fractions)
        greens.append(int(round(60*fraction)))
        green_records.append(dict(node=node, source_cycle=cycle, weighted_green_fraction=fraction,
                                  common_cycle_green=greens[-1]))
    other_rates = [max(0.0, (counts[i]-sum(through.values()))/duration) for i in range(3)]
    cross = [0.07]*3
    scenario = Scenario("RC3-1", 3, "bidirectional", greens_override=greens,
                        routes_override=[[[0, 1, 2], rates["forward"], "forward"],
                                         [[2, 1, 0], rates["reverse"], "reverse"]],
                        links_override=links, cross_rates=cross)
    report = dict(repository="https://github.com/Pi-Star-Lab/RESCO", commit=COMMIT,
                  network="cologne3", source_files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (SOURCE/"cologne3.net.xml", SOURCE/"cologne3.rou.xml")},
                  junctions=[dict(index=i, original_id=v.get("id"), x=float(v.get("x")), y=float(v.get("y")))
                             for i, v in enumerate(nodes)],
                  links=mappings, green_mapping=green_records, road_geometry=geometry,
                  source_vehicle_count=len(vehicles), departure_window_seconds=duration,
                  through_route_counts={str(k): v for k, v in through.items()},
                  through_rates=rates, other_route_rates_excluded=other_rates, cross_rates_used=cross,
                  transformations=["Retain vehicles visiting the three signals exactly once in west-to-east or east-to-west order.",
                     "Contract roads between consecutive signals; use mean lane length/speed travel times.",
                     "Use through-route counts over the observed departure window as stationary entry rates.",
                     "Exclude other signal-visit sequences. Retained endpoint turns and U-turns are aggregated into one coordinated movement per direction.",
                     "Use the controlled-case cross demand of 0.07 veh/s per signal; do not collapse all excluded movements into one queue.",
                     "Pool retained source movement green fractions, including endpoint turns and both G/g states; scale to a common 60-second cycle and round to seconds.",
                     "Use the same 0.5 veh/s saturation, storage and stochastic-arrival rules as the controlled cases."],
                  scenario=asdict(scenario))
    return scenario, report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mapping-only',action='store_true',help='Update map geometry without recalculating delay tables')
    args=parser.parse_args()
    scenario, report = extract()
    folder = ROOT / "results/resco"
    folder.mkdir(parents=True, exist_ok=True)
    if args.mapping_only and (folder/'provenance.json').exists():
        previous=json.loads((folder/'provenance.json').read_text())
        assert {k:v for k,v in previous.items() if k!='road_geometry'}=={k:v for k,v in report.items() if k!='road_geometry'}
    (folder/"provenance.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    if args.mapping_only:
        print('Derived source-road geometry added; all prior mapping fields unchanged; no tables rerun.')
        return
    for load, levels in [(v, 8) for v in (.65, 1, 1.35, 1.55)] + [(1, 4), (1, 2)]:
        spec = asdict(scenario)
        spec.update(name=f"RC3-{load:g}" if levels == 8 else f"RC3-C{levels}", load=load, states=levels)
        case = Scenario(**spec)
        table = build_tables(case)
        exact, offsets, costs = enumerate_case(table)
        (folder/f"{case.name}.json").write_text(json.dumps({**table, "exact": exact}, indent=2), encoding="utf8")
        np.savez_compressed(folder/f"{case.name}.npz", offsets=offsets, costs=costs)
        print(case.name, exact, flush=True)
    print(json.dumps({"greens":scenario.greens,"links":scenario.links(),"cross_rates":scenario.cross_rates},indent=2))


if __name__ == "__main__":
    main()
