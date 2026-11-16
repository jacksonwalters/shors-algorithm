import numpy as np
import pytest
from qiskit import QuantumCircuit, transpile
from qiskit.primitives import StatevectorSampler
from qiskit.quantum_info import Operator, Statevector

from shors_algorithm import order_finding_circuit
from shors_algorithm.hardware_circuits import (
    WORK_ENCODING_21, compiled_modular_exponentiation, compiled_order_finding_circuit,
)
from shors_algorithm.verification import analyze_counts, ideal_distribution


@pytest.mark.parametrize("modulus,counting_qubits", [(15, 4), (21, 5), (21, 6)])
def test_every_exponent_has_exact_modular_value_and_encoding_phase(modulus, counting_qubits):
    circuit = compiled_modular_exponentiation(modulus, counting_qubits)
    dimension = 1 << circuit.num_qubits
    for exponent in range(1 << counting_qubits):
        residue = pow(2, exponent, modulus)
        encoded, amplitude = WORK_ENCODING_21[residue] if modulus == 21 else (residue, 1)
        state = Statevector.from_int(exponent, dimension).evolve(circuit).data
        expected = np.zeros(dimension, dtype=complex)
        expected[exponent | (encoded << counting_qubits)] = amplitude
        np.testing.assert_allclose(state, expected, atol=1e-10)


def test_relative_phase_pair_is_controlled_order_three():
    circuit = QuantumCircuit(3)
    circuit.rccx(0, 1, 2)
    circuit.rccx(0, 2, 1)
    unitary = Operator(circuit).data
    np.testing.assert_allclose(np.linalg.matrix_power(unitary, 3), np.eye(8), atol=1e-10)
    np.testing.assert_allclose(unitary[:, ::2], np.eye(8)[:, ::2], atol=1e-10)


@pytest.mark.parametrize("modulus,counting_qubits", [(15, 4), (21, 4), (21, 5), (21, 6)])
def test_phase_distribution_matches_full_arithmetic_reference(modulus, counting_qubits):
    reference = order_finding_circuit(2, modulus, counting_qubits, measure=False)
    expected = Statevector.from_instruction(reference).probabilities(range(counting_qubits))
    np.testing.assert_allclose(ideal_distribution(modulus, counting_qubits), expected, atol=1e-10)


@pytest.mark.parametrize("modulus,max_cx", [(15, 30), (21, 45)])
def test_local_transpilation_budget_and_sampled_verification(modulus, max_cx):
    circuit = compiled_order_finding_circuit(modulus)
    compiled = transpile(circuit, basis_gates=["u", "cx"], optimization_level=3, seed_transpiler=7)
    assert compiled.count_ops().get("cx", 0) <= max_cx
    counts = StatevectorSampler(seed=7).run([compiled], shots=4096).result()[0].data.phase.get_counts()
    report = analyze_counts(counts, modulus, circuit.num_clbits)
    assert report["factors"] == ([3, 5] if modulus == 15 else [3, 7])
    assert report["passed"]


@pytest.mark.parametrize("modulus,counting_qubits", [(15, 4), (21, 5)])
def test_uniform_noise_fails_even_when_it_returns_correct_factors(modulus, counting_qubits):
    counts = {format(i, f"0{counting_qubits}b"): 128 for i in range(1 << counting_qubits)}
    report = analyze_counts(counts, modulus, counting_qubits)
    assert report["factors"] is not None
    assert not report["passed"]
    assert report["total_variation_from_uniform"] == 0


def test_uniform_ideal_cannot_be_used_for_hardware_verification():
    with pytest.raises(ValueError, match="uniform"):
        analyze_counts({"00": 32, "01": 32, "10": 32, "11": 32}, 15, 2)


def test_compiled_scope_is_explicit():
    with pytest.raises(ValueError, match="only 15 and 21"):
        compiled_order_finding_circuit(35)
