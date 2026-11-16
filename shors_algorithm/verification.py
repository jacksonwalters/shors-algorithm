"""Report factoring AND distribution quality; noisy factors alone are insufficient."""

from collections.abc import Mapping

import numpy as np
from qiskit.quantum_info import Statevector

from .hardware_circuits import compiled_order_finding_circuit
from .order_finding import factors_from_counts, recover_periods


def ideal_distribution(modulus: int, counting_qubits: int) -> np.ndarray:
    circuit = compiled_order_finding_circuit(modulus, counting_qubits, measure=False)
    probabilities = Statevector.from_instruction(circuit).probabilities(range(counting_qubits))
    return probabilities / probabilities.sum()


def analyze_counts(
    counts: Mapping[str, int], modulus: int, counting_qubits: int, *, bootstrap_samples: int = 10000
) -> dict:
    """Assess one compiled experiment using raw, unpostselected counts.

    Predeclared pass criterion: valid factors, closer to the ideal than to
    uniform in total variation, and p < .01 against the uniform null. The
    Monte Carlo null statistic is projection along (ideal - uniform), with
    a fixed seed. This assumes independent shots; it is not an entanglement
    witness, proof of speedup, or a test against all possible classical models.
    """
    periods = recover_periods(counts, 2, modulus, counting_qubits)  # Also validates counts.
    shots = sum(counts.values())
    if shots <= 0:
        raise ValueError("at least one measured shot is required")
    if not isinstance(bootstrap_samples, int) or bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be a positive integer")
    dimension = 1 << counting_qubits
    observed = np.zeros(dimension)
    for bitstring, count in counts.items():
        observed[int(bitstring, 2)] = count / shots
    ideal = ideal_distribution(modulus, counting_qubits)
    uniform = np.full(dimension, 1 / dimension)
    direction = ideal - uniform
    norm = float(direction @ direction)
    if norm < 1e-12:
        raise ValueError("use more counting qubits: this ideal distribution is uniform")
    score = float((observed - uniform) @ direction)
    rng = np.random.default_rng(7)
    null_counts = rng.multinomial(shots, uniform, size=bootstrap_samples)
    null_scores = (null_counts / shots - uniform) @ direction
    pvalue = float((1 + np.count_nonzero(null_scores >= score)) / (bootstrap_samples + 1))
    tvd_ideal = float(np.abs(observed - ideal).sum() / 2)
    tvd_uniform = float(np.abs(observed - uniform).sum() / 2)
    factors = factors_from_counts(counts, 2, modulus, counting_qubits)
    direct_successes = sum(
        count for bitstring, count in counts.items()
        if factors_from_counts({bitstring: count}, 2, modulus, counting_qubits) is not None
    )
    return {
        "modulus": modulus,
        "base": 2,
        "counting_qubits": counting_qubits,
        "shots": shots,
        "periods": list(periods),
        "factors": list(factors) if factors else None,
        "total_variation_from_ideal": tvd_ideal,
        "total_variation_from_uniform": tvd_uniform,
        "classical_fidelity": float(np.sum(np.sqrt(observed * ideal)) ** 2),
        "projected_visibility": float(np.clip(score / norm, 0, 1)),
        "uniform_null_pvalue": pvalue,
        "uniform_null_samples": bootstrap_samples,
        "single_outcome_factor_fraction": direct_successes / shots,
        "passed": bool(factors and tvd_ideal < tvd_uniform and pvalue < 0.01),
        "counts": dict(sorted(counts.items())),
        "ideal_probabilities": {format(i, f"0{counting_qubits}b"): float(p) for i, p in enumerate(ideal)},
    }
