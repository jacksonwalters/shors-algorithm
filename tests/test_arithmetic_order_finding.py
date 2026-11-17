import numpy as np
import pytest
from qiskit.quantum_info import Statevector

from shors_algorithm.arithmetic_order_finding import (
    arithmetic_modular_exponentiation, arithmetic_order_finding_circuit,
    arithmetic_phase_probabilities, evolve_basis_states, simulate_arithmetic,
)


@pytest.mark.parametrize("a,modulus", [(2, 15), (7, 15), (2, 21), (8, 21), (2, 35), (3, 35), (5, 33)])
def test_every_exponent_against_integer_arithmetic(a, modulus):
    circuit = arithmetic_modular_exponentiation(a, modulus)
    t = circuit.metadata["counting_qubits"]
    inputs = list(range(1 << t))
    # pow() is an independent TEST oracle. The simulator executes the gates.
    expected = [x | (pow(a, x, modulus) << t) for x in inputs]
    assert evolve_basis_states(circuit, inputs).tolist() == expected


@pytest.mark.parametrize("a,modulus,period", [(2, 15, 4), (2, 21, 6), (2, 35, 12), (5, 33, 10)])
def test_complete_distribution_against_independent_fourier_calculation(a, modulus, period):
    t = 2 * (modulus - 1).bit_length()
    dimension = 1 << t
    indices = np.arange(dimension)
    expected = sum(abs(np.fft.fft((indices % period == residue).astype(float)) / dimension) ** 2
                   for residue in range(period))
    np.testing.assert_allclose(arithmetic_phase_probabilities(a, modulus), expected, atol=1e-10)


@pytest.mark.parametrize("a,modulus,t", [(2, 3, 3), (2, 5, 3)])
def test_sparse_simulation_matches_full_qiskit_statevector(a, modulus, t):
    circuit = arithmetic_order_finding_circuit(a, modulus, t, measure=False)
    state = Statevector.from_instruction(circuit)
    expected = state.probabilities(range(t))
    np.testing.assert_allclose(arithmetic_phase_probabilities(a, modulus, t), expected, atol=1e-10)


@pytest.mark.parametrize("a,modulus,factors", [(2, 15, (3, 5)), (7, 15, (3, 5)), (2, 21, (3, 7)),
                                              (8, 21, (3, 7)), (2, 35, (5, 7)), (3, 35, (5, 7)), (5, 33, (3, 11))])
def test_factoring_with_unchanged_general_builder(a, modulus, factors):
    result = simulate_arithmetic(a, modulus, shots=2048, seed=7)
    assert result.factors == factors
    assert sum(result.counts.values()) == 2048
    assert result.counting_qubits == 2 * result.work_qubits
    assert result.scratch_qubits == 2 * result.work_qubits + 3


def test_unhelpful_base_does_not_invent_factors():
    result = simulate_arithmetic(4, 21, shots=2048)
    assert result.factors is None  # Minimal order is odd; its even multiples give halfway=1.


@pytest.mark.parametrize("a,t", [(1, 1), (1, 6), (2, 1), (6, 1), (34, 1), (2, 6)])
def test_short_precision_and_identity_base(a, t):
    circuit = arithmetic_modular_exponentiation(a, 35, t)
    inputs = list(range(1 << t))
    assert evolve_basis_states(circuit, inputs).tolist() == [
        x | (pow(a, x, 35) << t) for x in inputs
    ]


def test_aer_mps_is_an_independent_simulation_path():
    pytest.importorskip("qiskit_aer")
    result = simulate_arithmetic(2, 15, counting_qubits=6, shots=512, method="aer-mps")
    assert result.factors == (3, 5)
    assert sum(result.counts.values()) == 512
    observed = np.zeros(1 << result.counting_qubits)
    for bitstring, count in result.counts.items():
        observed[int(bitstring, 2)] = count / 512
    expected = arithmetic_phase_probabilities(2, 15, result.counting_qubits)
    assert np.abs(observed - expected).sum() / 2 < 0.15
