from math import gcd

import numpy as np
import pytest
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Operator

from shors_algorithm import controlled_modular_multiplication, modular_multiplication


def expected_operator(a, modulus, power=1, controlled=False):
    width = (modulus - 1).bit_length()
    offset = int(controlled)
    dimension = 1 << (width + offset)
    expected = np.zeros((dimension, dimension), dtype=complex)
    for column in range(dimension):
        x = column >> offset
        active = not controlled or (column & 1)
        output = pow(a, power, modulus) * x % modulus if active and x < modulus else x
        row = (output << offset) | (column & offset)
        expected[row, column] = 1
    return expected


CASES = [
    (a, modulus)
    for modulus in (2, 3, 5, 8, 10, 15, 16, 21)
    for a in range(1, modulus)
    if gcd(a, modulus) == 1
] + [(2, 33), (2, 35), (13, 35)]


@pytest.mark.parametrize("a,modulus", CASES)
@pytest.mark.parametrize("controlled", [False, True])
def test_entire_unitary_including_unused_states_and_phases(a, modulus, controlled):
    make_gate = controlled_modular_multiplication if controlled else modular_multiplication
    actual = Operator(make_gate(a, modulus)).data
    # Matrix equality, not just basis-state probabilities: relative phases
    # would corrupt phase estimation even if the truth table appeared correct.
    np.testing.assert_allclose(actual, expected_operator(a, modulus, controlled=controlled), atol=1e-10)


@pytest.mark.parametrize("power", [0, 1, 2, 4, 8, 16, 1024])
def test_controlled_powers(power):
    gate = controlled_modular_multiplication(2, 21, power)
    np.testing.assert_allclose(Operator(gate).data, expected_operator(2, 21, power, True), atol=1e-10)


def test_large_power_is_synthesized_as_one_constant_multiplier():
    # 2**(2**100) mod 21 = 16. Synthesis cost must not depend on the exponent.
    large = controlled_modular_multiplication(2, 21, 2**100)
    small = controlled_modular_multiplication(16, 21)
    assert large.definition == small.definition


def test_transpiled_multiplier_preserves_exact_action():
    circuit = QuantumCircuit(6)
    circuit.append(controlled_modular_multiplication(2, 21), range(6))
    compiled = transpile(circuit, basis_gates=["u", "cx"], optimization_level=1, seed_transpiler=7)
    assert set(compiled.count_ops()) <= {"u", "cx"}
    np.testing.assert_allclose(Operator(compiled).data, expected_operator(2, 21, controlled=True), atol=1e-9)


@pytest.mark.parametrize("a,modulus,power", [(3, 21, 1), (0, 15, 1), (2, 1, 1), (2, 21, -1), (2.5, 21, 1), (2, 21.5, 1), (True, 21, 1)])
def test_invalid_arguments(a, modulus, power):
    with pytest.raises(ValueError):
        modular_multiplication(a, modulus, power)
