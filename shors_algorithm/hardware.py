"""Prepare, submit once, and collect reproducible IBM hardware experiments.

Use saved Runtime credentials. No tokens or account details are written to
artifacts. All counts are raw: no postselection or readout correction.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from math import log1p
from pathlib import Path

from qiskit import qpy
from qiskit.transpiler import generate_preset_pass_manager

from .hardware_circuits import compiled_order_finding_circuit
from .verification import analyze_counts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, default=str) + "\n")
    temporary.replace(path)


def _service():
    from qiskit_ibm_runtime import QiskitRuntimeService
    return QiskitRuntimeService(instance="auto", plans_preference=["open"])


def circuit_resources(circuit, backend) -> dict:
    active = set()
    cost = 0.0
    missing = 0
    for instruction in circuit.data:
        name = instruction.operation.name
        if name == "barrier":
            continue
        qubits = tuple(circuit.find_bit(q).index for q in instruction.qubits)
        active.update(qubits)
        properties = backend.target[name].get(qubits) if name in backend.target else None
        error = properties.error if properties is not None else None
        if error is None:
            missing += 1
        elif error >= 1:
            cost = float("inf")
        else:
            cost -= log1p(-error)
    return {
        "active_physical_qubits": sorted(active),
        "two_qubit_gates": sum(len(inst.qubits) == 2 for inst in circuit.data),
        "two_qubit_depth": circuit.depth(lambda inst: len(inst.qubits) == 2),
        "depth": circuit.depth(),
        "operations": dict(circuit.count_ops()),
        # A ranking heuristic, not a predicted factoring success probability.
        "calibration_error_cost": cost,
        "instructions_without_error_data": missing,
        "initial_layout": circuit.layout.initial_index_layout(filter_ancillas=True),
        "final_layout": circuit.layout.final_index_layout(filter_ancillas=True),
    }


def prepare(directory: Path, backend_name: str, shots: int, noise_sim: bool) -> None:
    if shots < 1:
        raise ValueError("shots must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "prepare.json").exists() or (directory / "job.json").exists():
        raise ValueError("this experiment already exists; use a new directory")
    service = _service()
    backend = service.backend(backend_name)
    experiments = []
    circuits = []
    for modulus, counting in [(15, 4), (21, 4), (21, 5)]:
        logical = compiled_order_finding_circuit(modulus, counting)
        trials = []
        for seed in (7, 17, 37, 73):
            pm = generate_preset_pass_manager(backend=backend, optimization_level=3, seed_transpiler=seed)
            compiled = pm.run(logical)
            resources = circuit_resources(compiled, backend)
            trials.append((compiled, {"seed_transpiler": seed, **resources}))
        compiled, selected = min(
            trials,
            key=lambda trial: (
                trial[1]["calibration_error_cost"], trial[1]["two_qubit_gates"],
                trial[1]["two_qubit_depth"],
            ),
        )
        if selected["two_qubit_gates"] > 200 or selected["two_qubit_depth"] > 200:
            raise ValueError("compiled circuit exceeds this experiment's two-qubit budget")
        circuits.append(compiled)
        experiments.append({
            "modulus": modulus, "base": 2, "counting_qubits": counting,
            "logical_qubits": logical.num_qubits,
            "implementation": logical.metadata["implementation"],
            "selected": selected,
            "candidates": [resources for _, resources in trials],
        })
        print(f"N={modulus}, t={counting}: {selected['two_qubit_gates']} native two-qubit gates, "
              f"two-qubit depth {selected['two_qubit_depth']}", flush=True)
    qpy_path = directory / "circuits.qpy"
    with qpy_path.open("wb") as stream:
        qpy.dump(circuits, stream)
    manifest = {
        "schema_version": 1,
        "created_at": _now(),
        "backend": backend.name,
        "backend_calibration_time": str(backend.properties().last_update_date),
        "shots_per_circuit": shots,
        "maximum_job_execution_seconds": 120,
        "circuits_sha256": hashlib.sha256(qpy_path.read_bytes()).hexdigest(),
        "source_sha256": {
            name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ("hardware_circuits.py", "order_finding.py", "verification.py", "hardware.py")
        },
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("qiskit", "qiskit-ibm-runtime", "numpy")
        },
        "verification_rule": "valid factors AND TVD(ideal) < TVD(uniform) AND uniform-null p < 0.01",
        "counts_policy": "raw counts; no postselection, readout correction, or outcome filtering",
        "experiments": experiments,
    }
    if noise_sim:
        from qiskit_aer import AerSimulator
        simulator = AerSimulator.from_backend(
            backend, method="statevector", max_parallel_threads=4, max_memory_mb=4096
        )
        noise_result = simulator.run(circuits, shots=shots, seed_simulator=7).result()
        noise_reports = [
            analyze_counts(noise_result.get_counts(i), exp["modulus"], exp["counting_qubits"])
            for i, exp in enumerate(experiments)
        ]
        _write_json(directory / "noise_simulation.json", {
            "kind": "local calibration-based simulation, not hardware",
            "backend": backend.name, "experiments": noise_reports,
        })
        for report in noise_reports:
            print(f"Noise simulation N={report['modulus']}, t={report['counting_qubits']}: "
                  f"pass={report['passed']}, fidelity={report['classical_fidelity']:.3f}", flush=True)
    _write_json(directory / "prepare.json", manifest)
    print(f"Prepared {directory}; no job submitted.", flush=True)


def submit(directory: Path) -> None:
    if (directory / "job.json").exists():
        raise ValueError("a job is already recorded here; collect it instead of submitting again")
    manifest = json.loads((directory / "prepare.json").read_text())
    qpy_path = directory / "circuits.qpy"
    if hashlib.sha256(qpy_path.read_bytes()).hexdigest() != manifest["circuits_sha256"]:
        raise ValueError("the prepared circuits have changed")
    with qpy_path.open("rb") as stream:
        circuits = qpy.load(stream)
    if len(circuits) != len(manifest["experiments"]):
        raise ValueError("prepared circuit count does not match the manifest")
    from qiskit_ibm_runtime import SamplerV2
    backend = _service().backend(manifest["backend"])
    sampler = SamplerV2(mode=backend, options={
        "max_execution_time": manifest["maximum_job_execution_seconds"],
        "environment": {"job_tags": ["shor-15-21", "compiled-demonstration"]},
    })
    # Record the ID immediately so a later collect can resume after disconnects.
    job = sampler.run(circuits, shots=manifest["shots_per_circuit"])
    record = {"job_id": job.job_id(), "backend": backend.name, "submitted_at": _now()}
    _write_json(directory / "job.json", record)
    print(json.dumps(record), flush=True)


def collect(directory: Path) -> bool:
    manifest = json.loads((directory / "prepare.json").read_text())
    record = json.loads((directory / "job.json").read_text())
    job = _service().job(record["job_id"])
    status = job.status()
    print(f"Job {record['job_id']}: {status}", flush=True)
    if status in ("ERROR", "CANCELLED"):
        _write_json(directory / "failure.json", {"job_id": record["job_id"], "status": status, "message": job.error_message()})
        raise RuntimeError(f"hardware job ended with {status}; see failure.json")
    if status != "DONE":
        return False
    result = job.result()
    if len(result) != len(manifest["experiments"]):
        raise ValueError("result count does not match the submitted experiments")
    raw = {
        **record, "collected_at": _now(), "metrics": job.metrics(),
        "runtime_metadata": result.metadata,
        "experiments": [
            {"modulus": exp["modulus"], "counting_qubits": exp["counting_qubits"],
             "counts": pub.data.phase.get_counts(), "runtime_metadata": pub.metadata}
            for exp, pub in zip(manifest["experiments"], result)
        ],
    }
    _write_json(directory / "raw_counts.json", raw)
    reports = [analyze_counts(exp["counts"], exp["modulus"], exp["counting_qubits"])
               for exp in raw["experiments"]]
    _write_json(directory / "analysis.json", {
        **record, "analyzed_at": _now(), "verification_rule": manifest["verification_rule"],
        "analysis_source_sha256": hashlib.sha256(Path(__file__).with_name("verification.py").read_bytes()).hexdigest(),
        "experiments": reports,
    })
    for report in reports:
        print(f"N={report['modulus']}, t={report['counting_qubits']}: factors={report['factors']}, "
              f"passed={report['passed']}, fidelity={report['classical_fidelity']:.4f}, "
              f"TVD ideal={report['total_variation_from_ideal']:.4f}, "
              f"TVD uniform={report['total_variation_from_uniform']:.4f}", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "submit", "collect"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--backend", default="ibm_fez")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--noise-sim", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.directory, args.backend, args.shots, args.noise_sim)
    elif args.action == "submit":
        submit(args.directory)
    elif not collect(args.directory):
        return 2  # Still queued/running; collect again later without resubmitting.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
