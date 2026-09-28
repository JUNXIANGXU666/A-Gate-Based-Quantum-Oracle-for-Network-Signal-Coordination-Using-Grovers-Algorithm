# A Gate-Based Quantum Oracle for Network Signal Coordination Using Grover's Algorithm

Scientific code and experimental records for the study by Vinayak Dixit, Junxiang Xu and Richard Pech.

The construction evaluates queue-based link costs, adds them reversibly, compares the network cost with a prescribed limit and marks feasible signal offsets. Classical comparisons, PointQ traffic simulations and IBM hardware measurements have distinct roles in the evaluation.

## Contents

| Directory | Contents |
| --- | --- |
| `code/` | Queue tables, exact and budgeted optimisation, reversible and compiled quantum circuits, statistics and plotting |
| `scripts/` | PointQ execution wrapper, dependency setup and archive checks |
| `results/model/` | Nineteen finite traffic instances, all link tables and exact enumeration |
| `results/pointq_v2/` | The 288 formal PointQ results, paired-arrival hashes, sampled queue series and event-file provenance |
| `results/optimisation/` | Fifteen instances with 100 runs per budgeted method |
| `results/quantum/` | Gate-level correctness and noiseless amplification records |
| `results/hardware/` | Raw shot counts, native circuits, resource records and device calibration snapshots |
| `results/statistics/` | Derived comparisons, intervals and calibration summaries |

`MANIFEST.json` identifies the released files by SHA-256. The original large PointQ event logs are not distributed here. Their hashes, input generation and measurement code are provided so that the traffic simulations can be rerun. No third-party simulator source is redistributed.

## Environment

The experiments used Python 3.11.9. Install the pinned dependencies in a separate Python environment:

```sh
python -m pip install -r requirements.txt
```

Arial must be installed to reproduce the exact figure typography. The plotting script stops if Arial is unavailable, rather than silently changing fonts. Windows was used for the reported timings. Runtime comparisons on another computer need not reproduce those timings.

## Check the Archived Evidence

These commands run locally and do not submit quantum jobs:

```sh
python scripts/check_archive.py
python code/analyse_evidence.py
python code/generate_tables.py
python code/publication_figures.py
```

The first command checks file hashes, exact costs, common-arrival pairing, hardware counts and archived verification records. Subsequent commands regenerate numerical summaries, LaTeX tables and seven PDF/PNG figures. Generated artwork and tables appear in `manuscript/`. That directory is an output location, not a copy of the article.

## Rerun the Computations

Work on a separate copy to preserve the released results. Queue tables and optimisation comparisons can be regenerated with:

```sh
python code/traffic_model.py
python code/optimisation_experiments.py
python code/verify_quantum.py
```

`verify_quantum.py` executes the actual reversible gates. The reported 172 basis checks comprise 20 cost-accumulation tests and 152 bit/phase tests. The bit tests initialise the flag at zero. Grover statevector tests are recorded separately.

The adaptive Grover comparisons in `optimisation_experiments.py` sample ideal measurement probabilities. They are not hardware optimisation runs and do not establish a wall-clock speedup. Dynamic programming exploits the tested path and ring structure and provides an exact classical reference.

## PointQ

PointQ is an external traffic simulator maintained at [akurzhan/point-q](https://github.com/akurzhan/point-q). The study uses commit `769af12f47da7bbfe29570fd6c9da479e10381cb`. Install that version using Git:

```sh
python scripts/setup_pointq.py
```

The wrapper changes input configuration and seeds independent entry-arrival streams. It does not replace the engine's queue or departure equations. The input generator converts the saturation rate from vehicles per second to vehicles per 0.1-second PointQ time unit.

To rerun all 288 cases, use a separate copy without the archived per-run `results/pointq_v2/v2_*.json` files and without prior `pq/` completion files, then run:

```sh
python code/run_pointq_suite.py
```

The suite is restartable and skips completed cases. Each scenario uses eight common-arrival seeds across equal offsets, forward progression and the queue-table optimum. The traffic evidence includes cases where forward progression outperforms the queue-table plan. The pairwise objective uses frozen local release profiles, whereas PointQ propagates arrivals and represents finite storage.

## IBM Hardware

The archived experiment contains 15 completed jobs on `ibm_fez`, 180 circuit executions and 737,280 shots. Its total measured quantum usage is 495 seconds. `seed_11.qpy`, `seed_29.qpy` and `seed_47.qpy` are the native-gate circuits used in those jobs. Count files retain job IDs and all measured bit strings. Account and billing records are excluded.

Reproducing the archived summaries requires no IBM account. Acquiring new data requires a separately configured Qiskit Runtime account, an accessible backend and sufficient quantum allowance. Device calibration and available backends change, so new results will not be numerically identical.

In a fresh acquisition directory with the model results copied over, the acquisition sequence is:

```sh
python code/prepare_hardware.py
python code/validate_hardware_inputs.py
python code/run_hardware.py --execute
```

The validation step aligns baseline initial layouts with the amplified circuits and checks all twelve seed-11 native circuits noiselessly. The final command explicitly authorises quantum execution and enforces the study's usage guard. Do not run it merely to regenerate plots. Never add your local Runtime credentials or account-quota files to version control.

## Attribution and Scope

Qiskit, NumPy, SciPy, Matplotlib and PointQ remain third-party dependencies governed by their respective terms. PointQ should be cited through its original source and associated literature, including Lioris et al., *Transportation Research Part C* 77, 292-305, DOI [10.1016/j.trc.2017.01.023](https://doi.org/10.1016/j.trc.2017.01.023).

The full reversible oracle and the enumeration-based compiled phase diagnostic are separate implementations. The latter tests amplification with reduced arithmetic cost and is not presented as a scalable replacement for the reversible construction. The hardware boundary applies to the documented instances, layouts, shot counts and device conditions.
