"""Bounded, read-only IBM feasibility check for N=35, base=2.

Compare two phase precisions and three compiler configurations. Save device
calibrations, routing resources, timing, and error-cost diagnostics. This is
not a noisy circuit simulation and never submits a hardware job.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from math import log
from pathlib import Path
from statistics import median
from time import perf_counter

from qiskit.transpiler import generate_preset_pass_manager

from .arithmetic_order_finding import arithmetic_order_finding_circuit
from .hardware import _service, circuit_resources


def calibration_diagnostics(circuit, backend, resources):
    """Save the actual instruction data behind the cost/timing estimates.

    Average gate error is not a per-shot failure probability. Its product
    is a screening heuristic, with no claim to predict factoring success.
    Timing is a gate-duration critical path, excluding shot repetition and
    control-system overhead. T1/T2 comparisons are likewise diagnostics.
    """
    used = {}
    for instruction in circuit.data:
        name = instruction.operation.name
        if name == "barrier":
            continue
        qubits = tuple(circuit.find_bit(q).index for q in instruction.qubits)
        key = (name, qubits)
        if key not in used:
            prop = backend.target[name].get(qubits)
            used[key] = {
                "instruction": name, "qubits": list(qubits), "occurrences": 0,
                "average_error": prop.error if prop is not None else None,
                "duration_seconds": prop.duration if prop is not None else None,
            }
        used[key]["occurrences"] += 1
    properties = backend.properties()
    coherence = [{"qubit": q, "t1_seconds": properties.t1(q), "t2_seconds": properties.t2(q)}
                 for q in resources["active_physical_qubits"]]
    median_t1 = median(q["t1_seconds"] for q in coherence)
    median_t2 = median(q["t2_seconds"] for q in coherence)
    duration = circuit.estimate_duration(backend.target)
    two_qubit = [item for item in used.values() if len(item["qubits"]) == 2]
    error_data_complete = all(item["average_error"] is not None for item in two_qubit)
    mean_error = (sum(item["occurrences"] * item["average_error"] for item in two_qubit)
                  / resources["two_qubit_gates"] if error_data_complete and two_qubit else None)
    return {
        "interpretation": "calibrated screening heuristics, not a noisy simulation or success probability",
        "gate_duration_critical_path_seconds": duration,
        "median_active_t1_seconds": median_t1,
        "median_active_t2_seconds": median_t2,
        "duration_over_median_t1": duration / median_t1,
        "duration_over_median_t2": duration / median_t2,
        "usage_weighted_two_qubit_average_error": mean_error,
        "log10_gate_fidelity_product_heuristic": (
            -resources["calibration_error_cost"] / log(10)
            if resources["instructions_without_error_data"] == 0 else None
        ),
        "instruction_calibrations": list(used.values()),
        "active_qubit_coherence": coherence,
    }


def assess(backend_name, output):
    if output.exists():
        raise ValueError("use a new output filename to preserve the previous assessment")
    backend = _service().backend(backend_name)
    # Initialize target/properties once, so every candidate uses the same snapshot.
    _ = backend.target
    report = {
        "kind": "bounded general-arithmetic feasibility assessment",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "modulus": 35, "base": 2, "backend": backend.name,
        "calibration_time": str(backend.properties().last_update_date),
        "hardware_job_submitted": False,
        "versions": {name: importlib.metadata.version(name)
                     for name in ("qiskit", "qiskit-ibm-runtime")},
        "source_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("arithmetic.py", "arithmetic_order_finding.py", "hardware.py", "feasibility.py")
        },
        "screening_limits": {
            "two_qubit_gates": 200, "two_qubit_depth": 200,
            "description": "same conservative circuit budget as the previous 15/21 demonstrations; not a physical impossibility threshold",
        },
        "experiments": [],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    for t in (6, 12):
        logical = arithmetic_order_finding_circuit(2, 35, t)
        trials = []
        selected_circuit, selected_resources = None, None
        for level, seed in ((1, 7), (3, 7), (3, 17)):
            start = perf_counter()
            pm = generate_preset_pass_manager(backend=backend, optimization_level=level,
                                             seed_transpiler=seed)
            native = pm.run(logical)
            resources = circuit_resources(native, backend)
            trial = {"optimization_level": level, "seed_transpiler": seed,
                     "compilation_seconds": perf_counter() - start, **resources}
            trials.append(trial)
            if selected_resources is None or (
                trial["calibration_error_cost"], trial["two_qubit_gates"], trial["two_qubit_depth"]
            ) < (
                selected_resources["calibration_error_cost"], selected_resources["two_qubit_gates"],
                selected_resources["two_qubit_depth"],
            ):
                selected_circuit, selected_resources = native, trial
            print(f"t={t}, level={level}, seed={seed}: "
                  f"{resources['two_qubit_gates']} two-qubit gates, "
                  f"depth {resources['two_qubit_depth']}", flush=True)
        selected = {**selected_resources,
                    "diagnostics": calibration_diagnostics(selected_circuit, backend, selected_resources)}
        report["experiments"].append({
            "counting_qubits": t, "logical_qubits": logical.num_qubits,
            "selected": selected, "candidates": trials,
            "within_existing_hardware_budget": (
                selected["two_qubit_gates"] <= report["screening_limits"]["two_qubit_gates"]
                and selected["two_qubit_depth"] <= report["screening_limits"]["two_qubit_depth"]
            ),
        })
        output.write_text(json.dumps(report, indent=2) + "\n")
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="ibm_fez")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assess(args.backend, args.output)


if __name__ == "__main__":
    main()
