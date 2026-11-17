from math import gcd

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

from shors_algorithm.arithmetic import constant_adder, modular_adder, multiply_accumulate, arithmetic_modular_multiplication
from shors_algorithm.arithmetic_order_finding import evolve_basis_states


@pytest.mark.parametrize("width", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("constant", [-7, -1, 0, 1, 3, 16])
@pytest.mark.parametrize("controlled", [False, True])
def test_signed_constant_addition_and_clean_carries(width, constant, controlled):
    circuit = constant_adder(constant, width, controlled=controlled)
    offset = int(controlled)
    inputs = list(range(1 << (width + offset)))
    expected = [
        (((i >> offset) + constant * ((i & 1) if controlled else 1)) % (1 << width) << offset)
        | (i & offset)
        for i in inputs
    ]
    assert evolve_basis_states(circuit, inputs).tolist() == expected


@pytest.mark.parametrize("modulus", [2, 3, 4, 7, 8, 15, 21, 33, 35])
@pytest.mark.parametrize("controlled", [False, True])
def test_every_modular_addend_and_input(modulus, controlled):
    offset = int(controlled)
    inputs = list(range(modulus << offset))
    for constant in range(modulus):
        circuit = modular_adder(constant, modulus, controlled=controlled)
        expected = [
            (((i >> offset) + constant * ((i & 1) if controlled else 1)) % modulus << offset)
            | (i & offset)
            for i in inputs
        ]
        assert evolve_basis_states(circuit, inputs).tolist() == expected
        assert evolve_basis_states(circuit.inverse(), expected).tolist() == inputs


@pytest.mark.parametrize("modulus", [3, 5, 8, 15, 21, 35])
@pytest.mark.parametrize("a", [0, 1, 2, 3])
def test_accumulate_with_nonzero_accumulator_and_all_source_values(modulus, a):
    n = (modulus - 1).bit_length()
    inputs, expected = [], []
    for x in range(1 << n):
        for y in range(modulus):
            for control in (0, 1):
                inputs.append(control | (x << 1) | (y << (n + 1)))
                expected.append(control | (x << 1) | (((y + control * a * x) % modulus) << (n + 1)))
    circuit = multiply_accumulate(a, modulus)
    assert evolve_basis_states(circuit, inputs).tolist() == expected


@pytest.mark.parametrize("modulus", [2, 3, 5, 7, 8, 15, 16, 21, 33, 35])
@pytest.mark.parametrize("guard_invalid", [False, True])
def test_every_coprime_multiplier_control_and_unused_state(modulus, guard_invalid):
    n = (modulus - 1).bit_length()
    inputs = list(range((1 << (n + 1)) if guard_invalid else 2 * modulus))
    for a in range(1, modulus):
        if gcd(a, modulus) != 1:
            continue
        circuit = arithmetic_modular_multiplication(a, modulus, guard_invalid=guard_invalid).definition
        assert circuit.num_qubits == 3 * n + 4 + int(guard_invalid)
        expected = [
            2 * ((a * (i // 2) % modulus) if i % 2 and i // 2 < modulus else i // 2) + i % 2
            for i in inputs
        ]
        # Equality of full indices checks every scratch bit, including the
        # accumulator, carry chain, borrow, active, and enable flags.
        assert evolve_basis_states(circuit, inputs).tolist() == expected


@pytest.mark.parametrize("power", [0, 1, 2, 4, 8, 1024, 2**40])
def test_powers_use_classically_squared_constants(power):
    N, a = 21, 2
    circuit = arithmetic_modular_multiplication(a, N, power).definition
    inputs = list(range(64))
    expected = [2 * ((pow(a, power, N) * (i // 2) % N) if i % 2 and i // 2 < N else i // 2) + i % 2 for i in inputs]
    assert evolve_basis_states(circuit, inputs).tolist() == expected


def assert_qiskit_superposition(circuit, mapping):
    # Independent Qiskit simulation with complex amplitudes checks phases,
    # interference, and leakage, not just the classical truth table.
    rng = np.random.default_rng(7)
    amplitudes = rng.normal(size=len(mapping)) + 1j * rng.normal(size=len(mapping))
    amplitudes /= np.linalg.norm(amplitudes)
    initial = np.zeros(1 << circuit.num_qubits, dtype=complex)
    expected = np.zeros_like(initial)
    for (source, target), amplitude in zip(mapping.items(), amplitudes):
        initial[source] = amplitude
        expected[target] = amplitude
    actual = Statevector(initial).evolve(circuit).data
    np.testing.assert_allclose(actual, expected, atol=1e-10)


@pytest.mark.parametrize("constant", [-7, 3])
def test_adder_complex_superposition_in_qiskit(constant):
    circuit = constant_adder(constant, 4, controlled=True)
    mapping = {2 * x + c: 2 * ((x + constant * c) % 16) + c for x in range(16) for c in (0, 1)}
    assert_qiskit_superposition(circuit, mapping)


@pytest.mark.parametrize("modulus,constant", [(5, 3), (7, -2), (21, 13)])
def test_modular_adder_complex_superposition_in_qiskit(modulus, constant):
    circuit = modular_adder(constant, modulus, controlled=True)
    mapping = {2 * x + c: 2 * ((x + constant * c) % modulus) + c for x in range(modulus) for c in (0, 1)}
    assert_qiskit_superposition(circuit, mapping)


@pytest.mark.parametrize("modulus,a", [(3, 2), (5, 2), (7, 3)])
@pytest.mark.parametrize("guard_invalid", [False, True])
def test_multiplier_complex_superposition_in_qiskit(modulus, a, guard_invalid):
    circuit = arithmetic_modular_multiplication(a, modulus, guard_invalid=guard_invalid).definition
    dimension = (1 << (modulus - 1).bit_length()) if guard_invalid else modulus
    mapping = {2 * x + c: 2 * ((a * x % modulus) if c and x < modulus else x) + c
               for x in range(dimension) for c in (0, 1)}
    assert_qiskit_superposition(circuit, mapping)


def test_sparse_engine_rejects_phase_gates_instead_of_silently_ignoring_them():
    circuit = QuantumCircuit(2)
    circuit.p(0.3, 0)
    with pytest.raises(ValueError):
        evolve_basis_states(circuit, [0, 1])


@pytest.mark.parametrize("a,modulus,power", [(3, 21, 1), (2, 1, 1), (2, 21, -1), (2.5, 21, 1)])
def test_invalid_multiplier_arguments(a, modulus, power):
    with pytest.raises(ValueError):
        arithmetic_modular_multiplication(a, modulus, power)
