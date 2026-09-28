"""Reversible link-table accumulation and threshold marking using Qiskit gates."""
from __future__ import annotations

from itertools import product
import math

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import DiagonalGate, PhaseGate
from qiskit.synthesis.qft import synth_qft_full

from traffic_model import evaluate


def register_costs(table):
    C, n = table["scenario"]["states"], table["scenario"]["n"]
    q = int(math.log2(C))
    assert 2**q == C
    state = np.arange(C**(n-1))
    offsets = np.column_stack([np.zeros(len(state),dtype=int)]+[(state >> (q*(i-1))) % C for i in range(1,n)])
    return evaluate(table,offsets).astype(int), offsets


def reduction(table):
    rows = np.array(table["integer"], dtype=int)
    base = rows.min(axis=1)
    reduced = rows-base[:,None]
    divisor = int(np.gcd.reduce(reduced.ravel())) or 1
    reduced //= divisor
    bound = int(reduced.max(axis=1).sum())
    return reduced, int(base.sum()), divisor, max(1,bound.bit_length()), bound


def cost_computation(table):
    C, n = table["scenario"]["states"], table["scenario"]["n"]
    q = int(math.log2(C))
    nq = (n-1)*q
    rows, base, divisor, b, bound = reduction(table)
    circuit = QuantumCircuit(nq+b, name="link delay sum")
    accumulator = list(range(nq,nq+b))
    circuit.h(accumulator)
    for edge, costs in zip(table["links"],rows):
        nodes = [i for i in (edge["i"],edge["j"]) if i!=0]
        controls = [q*(i-1)+j for i in nodes for j in range(q)]
        for values in product(range(C),repeat=len(nodes)):
            assignment = {0:0,**dict(zip(nodes,values))}
            c = int(costs[(assignment[edge["i"]]-assignment[edge["j"]]) % C])
            state = sum(v << (i*q) for i,v in enumerate(values))
            for j,target in enumerate(accumulator):
                denominator = 2**(b-j)
                angle = 2*np.pi*(c % denominator)/denominator
                if abs(angle)>1e-14:
                    circuit.append(PhaseGate(angle).control(len(controls),ctrl_state=state),controls+[target])
    circuit.compose(synth_qft_full(b, inverse=True), accumulator, inplace=True)
    return circuit, dict(offset_qubits=nq,sum_qubits=b,base=base,divisor=divisor,sum_bound=bound)


def prefix_blocks(stop):
    start = 0
    while start < stop:
        size = (start & -start) if start else 1 << (stop.bit_length()-1)
        while start+size > stop:
            size //= 2
        yield start, int(math.log2(size))
        start += size


def mark_interval(circuit, qubits, threshold, flag=None):
    b = len(qubits)
    if threshold < 0:
        return
    stop = min(threshold+1,2**b)
    for start,free_bits in prefix_blocks(stop):
        controls = qubits[free_bits:]
        zero_bits = [qubits[j] for j in range(free_bits,b) if not ((start>>j)&1)]
        if zero_bits:
            circuit.x(zero_bits)
        if flag is not None:
            if controls:
                circuit.mcx(controls,flag)
            else:
                circuit.x(flag)
        elif not controls:
            circuit.global_phase += np.pi
        elif len(controls)==1:
            circuit.z(controls[0])
        else:
            circuit.mcp(np.pi,controls[:-1],controls[-1])
        if zero_bits:
            circuit.x(zero_bits)


def reversible_oracle(table, threshold, bit=False):
    compute, meta = cost_computation(table)
    circuit = QuantumCircuit(compute.num_qubits+int(bit), name="NSC oracle")
    circuit.compose(compute, range(compute.num_qubits),inplace=True)
    reduced_threshold = (threshold-meta["base"])//meta["divisor"]
    mark_interval(circuit,list(range(meta["offset_qubits"],compute.num_qubits)),reduced_threshold,
                  circuit.num_qubits-1 if bit else None)
    circuit.compose(compute.inverse(),range(compute.num_qubits),inplace=True)
    return circuit,meta


def compiled_oracle(table, threshold):
    costs,_ = register_costs(table)
    nq = int(math.log2(len(costs)))
    circuit = QuantumCircuit(nq,name="enumerated phase diagnostic")
    circuit.append(DiagonalGate(np.where(costs <= threshold,-1,1).astype(complex)),range(nq))
    return circuit,dict(offset_qubits=nq,sum_qubits=0)


def grover(table, threshold, iterations, route="reversible", measurement=False):
    oracle,meta = reversible_oracle(table,threshold) if route=="reversible" else compiled_oracle(table,threshold)
    nq = meta["offset_qubits"]
    c = QuantumCircuit(oracle.num_qubits)
    c.h(range(nq))
    for _ in range(iterations):
        c.compose(oracle,inplace=True)
        c.h(range(nq))
        c.x(range(nq))
        if nq==1:
            c.z(0)
        else:
            c.mcp(np.pi,list(range(nq-1)),nq-1)
        c.x(range(nq))
        c.h(range(nq))
        c.global_phase += np.pi
    if measurement:
        from qiskit import ClassicalRegister
        c.add_register(ClassicalRegister(nq,"offset"))
        c.measure(range(nq),range(nq))
    return c,meta
