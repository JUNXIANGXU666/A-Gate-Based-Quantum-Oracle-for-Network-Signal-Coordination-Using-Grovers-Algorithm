"""Generate fixed-time PointQ inputs without modifying the upstream engine."""
from __future__ import annotations

import json
from pathlib import Path

from traffic_model import Scenario


def write_rows(folder, filename, rows, header=None):
    text = ((header + "\n") if header is not None else "")
    text += "".join(" ".join(map(str, row)) + "\n" for row in rows)
    (folder/filename).write_text(text, encoding="ascii")


def generate(scenario: Scenario, offsets, folder: Path, stochastic=True, capacity=60):
    network = folder/"network"
    control = folder/"control"
    network.mkdir(parents=True, exist_ok=True)
    control.mkdir(exist_ok=True)
    links, movements, demand, paths = [], [], [], []
    entry, exit_links = {}, {}
    next_id = 1
    edge_map = {(edge["i"], edge["j"]): edge for edge in scenario.links()}
    routes = list(scenario.routes())
    rates = scenario.cross_rates if scenario.cross_rates is not None else [0.07]*scenario.n
    routes.extend([([i], rates[i]*scenario.load, "cross") for i in range(scenario.n)])
    for route, flow, direction in routes:
        ids = []
        for a, b in zip([-1]+route, route+[-1]):
            travel = edge_map[a, b]["travel"] if a >= 0 and b >= 0 else 0
            links.append([next_id, a+1 if a>=0 else -1, b+1 if b>=0 else -1,
                          max(1, travel*12), capacity if a>=0 and b>=0 else 0, travel])
            ids.append(next_id)
            next_id += 1
        entry.setdefault(route[0]+1, []).append(ids[0])
        exit_links.setdefault(route[-1]+1, []).append(ids[-1])
        demand.append([ids[0], flow])
        for node, a, b in zip(route, ids, ids[1:]):
            movements.append(dict(node=node+1, a=a, b=b, stage=2 if direction=="cross" else 1))
        paths.append(dict(direction=direction, nodes=route, links=ids, flow=flow))
    write_rows(network, "fi_demand_param_entry_link.txt", demand)
    write_rows(network, "fi_id_all_network_link_id_orig_dest_node_length_link_capacity_link_param_travel_duration.txt", links)
    write_rows(network, "fi_id_internal_link_id_orig_dest_node.txt", [v[:3] for v in links if v[1]>0 and v[2]>0])
    write_rows(network, "fi_id_node_id_entering_links_to_node.txt", [[i]+[v[0] for v in links if v[2]==i] for i in range(1, scenario.n+1)])
    write_rows(network, "fi_id_node_id_leaving_links_from_node.txt", [[i]+[v[0] for v in links if v[1]==i] for i in range(1, scenario.n+1)])
    write_rows(network, "fi_id_node_id_entry_links_to_network.txt", [[i]+v for i,v in entry.items()])
    write_rows(network, "fi_id_node_id_exit_links_from_network.txt", [[i]+v for i,v in exit_links.items()])
    allowed = {(m["a"],m["b"]) for m in movements}
    phases = [[a[0],b[0],capacity,scenario.saturation*0.1 if (a[0],b[0]) in allowed else 0,0]
              for a in links for b in links if a[2]>0 and a[2]==b[1]]
    write_rows(network, "fi_id_all_phases_max_queue_size_sat_flow_queue_type.txt",
               phases, "incoming outgoing capacity saturation_per_0.1s queue_type")
    for filename in ["fi_mrp.txt", "fi_mrp_cum.txt"]:
        write_rows(network, filename, [[m["a"],m["b"],1.0] for m in movements], "incoming outgoing probability")
    write_rows(network, "fi_id_node_type_node.txt", [[i,1] for i in range(1,scenario.n+1)], "node type")
    stages = []
    for i in range(1,scenario.n+1):
        for stage in [1,2]:
            stages.append([i]+[v for m in movements if m["node"]==i and m["stage"]==stage for v in (m["a"],m["b"])])
    write_rows(network, "fi_stages_each_sign_inters.txt", stages, "node phase_pairs")
    for filename in ["fi_stages_each_non_sign_inters.txt", "fi_series_varying_rp.txt", "fi_series_cum_val_varying_rp.txt",
                     "fi_init_state_que.txt", "fi_phase_interference.txt", "fi_demand_param_variation.txt"]:
        write_rows(network, filename, [], "no entries")
    write_rows(network, "fi_rout_type_entry_lk_mixed_manag.txt", [[d[0],1] for d in demand], "entry routing_type")
    write_rows(control, "fi_node_id_ctrl_type_category.txt", [[i,2,"without_sensor_requirement",0] for i in range(1,scenario.n+1)], "node type category estimate")
    rows = [[1], [v for i, offset in enumerate(offsets) for v in (i+1, offset*scenario.cycle/scenario.states)]]
    for i, green in enumerate(scenario.greens):
        rows.extend([[i+1,1,green,scenario.cycle],[i+1,0,3,scenario.cycle],
                     [i+1,2,scenario.cycle-green-6,scenario.cycle],[i+1,0,3,scenario.cycle]])
    write_rows(control, "File_FT_Offset_Control_Alg_Param.txt", rows, "fixed-time offsets and stages")
    settings = {"val_type_veh_final_dest":1,"val_indicating_stoch_demand":int(stochastic),
                "val_finite_capacity_internal_links":1,"cycle_duration":scenario.cycle}
    (folder/"settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (folder/"network_manifest.json").write_text(json.dumps({"scenario":vars(scenario),"offsets":list(map(int,offsets)),
                    "paths":paths,"links":links,"movements":movements}, indent=2), encoding="utf-8")
    return network, control, folder/"settings.json"


if __name__ == "__main__":
    generate(Scenario("B4-1",4,"bidirectional"), [0,0,0,0], Path(__file__).resolve().parents[1]/"configs/pq_trial")
