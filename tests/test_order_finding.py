import numpy as np
import pytest
from qiskit.quantum_info import Statevector

from shors_algorithm import (
    factors_from_counts,
    factors_from_period,
    order_finding_circuit,
    recover_periods,
    simulate,
)


@pytest.mark.parametrize("a,modulus,period,counting_qubits", [(7, 15, 4, 8), (2, 21, 6, 10)])
def test_full_phase_distribution(a, modulus, period, counting_qubits):
    circuit = order_finding_circuit(a, modulus, counting_qubits, measure=False)
    actual = Statevector.from_instruction(circuit).probabilities(list(range(counting_qubits)))
    # Independently compute the Fourier probabilities of periodic residue
    # classes. This checks all outcomes, including non-binary fractions for 21.
    dimension = 1 << counting_qubits
    indices = np.arange(dimension)
    expected = sum(
        np.abs(np.fft.fft((indices % period == residue).astype(float)) / dimension) ** 2
        for residue in range(period)
    )
    np.testing.assert_allclose(actual, expected, atol=1e-10)


@pytest.mark.parametrize("a,modulus,factors,period", [(7, 15, (3, 5), 4), (2, 21, (3, 7), 6)])
def test_local_sampler_factors_without_credentials(a, modulus, factors, period):
    result = simulate(a, modulus, shots=1024, seed=7)
    assert result.factors == factors
    assert period in result.periods
    assert sum(result.counts.values()) == 1024
    assert result.work_qubits == (modulus - 1).bit_length()
    assert result.counting_qubits == 2 * result.work_qubits


def test_phase_comes_from_bitstring_not_shot_count():
    counts = {format(171, "010b"): 1}
    assert recover_periods(counts, 2, 21, 10) == (6,)
    assert factors_from_counts(counts, 2, 21, 10) == (3, 7)
    assert factors_from_counts({format(171, "010b"): 999}, 2, 21, 10) == (3, 7)


def test_reduced_phases_need_combining_without_classical_order_search():
    half = {format(512, "010b"): 10}
    third = {format(341, "010b"): 10}
    assert recover_periods(half, 2, 21, 10) == ()
    assert recover_periods(third, 2, 21, 10) == ()
    assert recover_periods(half | third, 2, 21, 10) == (6,)


@pytest.mark.parametrize("counts", [{}, {"0000000000": 2048}, {format(171, "010b"): 0}])
def test_no_informative_samples_produce_no_factors(counts):
    assert factors_from_counts(counts, 2, 21, 10) is None


@pytest.mark.parametrize("a,modulus,period", [(2, 21, 3), (2, 21, 2), (2, 21, 12), (20, 21, 2), (4, 21, 3), (2, 7, 3)])
def test_unhelpful_or_invalid_periods_produce_no_factors(a, modulus, period):
    assert factors_from_period(a, modulus, period) is None


@pytest.mark.parametrize("counts", [{"10": 1}, {"xxxxxxxxxx": 1}, {"0000000000": -1}, {"0000000000": 1.5}, {17: 1}])
def test_malformed_counts_are_rejected(counts):
    with pytest.raises(ValueError):
        recover_periods(counts, 2, 21, 10)


@pytest.mark.parametrize("counting_qubits", [0, -1, 1.5])
def test_invalid_register_size(counting_qubits):
    with pytest.raises(ValueError):
        order_finding_circuit(2, 21, counting_qubits)
