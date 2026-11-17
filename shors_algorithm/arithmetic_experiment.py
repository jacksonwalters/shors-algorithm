"""Run general arithmetic factoring locally and optionally compile for a QPU.

This module never submits hardware jobs. --backend only reads calibration
data and transpiles. The existing hardware.py runner is for compiled demos.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
from time import perf_counter

from qiskit import transpile

from .arithmetic_order_finding import arithmetic_order_finding_circuit, simulate_arithmetic


def resource_report(circuit, backend_name=None):
    start = perf_counter()
    primitive = transpile(circuit, basis_gates=["x", "h", "cx", "ccx", "cswap", "cp", "swap"],
                          optimization_level=0)
    compiled = transpile(circuit, basis_gates=["u", "cx"], optimization_level=1, seed_transpiler=7)
    report = {
        "logical_qubits": circuit.num_qubits,
        "primitive_operations": dict(primitive.count_ops()),
        "all_to_all": {
            "basis": ["u", "cx"], "optimization_level": 1, "seed_transpiler": 7,
            "cx_gates": compiled.count_ops().get("cx", 0),
            "two_qubit_depth": compiled.depth(lambda instruction: len(instruction.qubits) == 2),
            "depth": compiled.depth(),
        },
    }
    if backend_name:
        from qiskit.transpiler import generate_preset_pass_manager
        from .hardware import _service, circuit_resources
        backend = _service().backend(backend_name)
        pm = generate_preset_pass_manager(backend=backend, optimization_level=1, seed_transpiler=7)
        native = pm.run(circuit)
        report["device_compilation"] = {
            "backend": backend.name,
            "calibration_time": str(backend.properties().last_update_date),
            "optimization_level": 1, "seed_transpiler": 7,
            **circuit_resources(native, backend),
            "hardware_job_submitted": False,
        }
    report["compilation_seconds"] = perf_counter() - start
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number", type=int, default=35)
    parser.add_argument("--base", type=int, default=2)
    parser.add_argument("--counting-qubits", type=int)
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--method", choices=("sparse", "aer-mps"), default="sparse")
    parser.add_argument("--resources", action="store_true")
    parser.add_argument("--backend", help="optional real-device compilation only; never submits")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    # This project's final experimental scope is N <= 35; the builder remains general.
    if not 2 <= args.number <= 35 or (args.counting_qubits is not None and not 1 <= args.counting_qubits <= 14):
        parser.error("this experiment CLI supports 2 <= N <= 35 and 1..14 counting bits")
    try:
        result = simulate_arithmetic(args.base, args.number, counting_qubits=args.counting_qubits,
                                     shots=args.shots, seed=args.seed, method=args.method)
    except ValueError as exc:
        parser.error(str(exc))
    report = {
        "kind": "ideal local simulation of general ripple-carry arithmetic",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed, "result": asdict(result),
        "versions": {name: importlib.metadata.version(name) for name in ("qiskit", "numpy")},
        "source_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("arithmetic.py", "arithmetic_order_finding.py", "order_finding.py")
        },
    }
    if args.method == "aer-mps":
        report["versions"]["qiskit-aer"] = importlib.metadata.version("qiskit-aer")
        report["mps_settings"] = {"truncation_threshold": 1e-16, "maximum_bond_dimension": None}
    print(f"N={result.modulus}, a={result.base}, method={result.method}", flush=True)
    print(f"Qubits: {result.counting_qubits} counting + {result.work_qubits} work + "
          f"{result.scratch_qubits} scratch", flush=True)
    print(f"Periods: {result.periods}; factors: {result.factors}; "
          f"simulation: {result.elapsed_seconds:.2f}s", flush=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    if args.resources or args.backend:
        circuit = arithmetic_order_finding_circuit(args.base, args.number, args.counting_qubits)
        report["resources"] = resource_report(circuit, args.backend)
        print(json.dumps(report["resources"], indent=2), flush=True)
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if result.factors is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
