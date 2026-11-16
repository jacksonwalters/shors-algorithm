"""Exact, ancilla-free modular multiplication for small demonstration circuits.

This synthesizes a permutation of computational basis states, not a permutation
of qubit wires. Its cost is exponential in the bit length of the modulus;
scalable Shor implementations need reversible arithmetic instead.
"""

from math import gcd
from operator import index

from qiskit import QuantumCircuit
from qiskit.circuit import Gate
from qiskit.circuit.library import MCXGate


def _integer(value: int, name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        value = index(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _validate_modulus(a: int, modulus: int) -> tuple[int, int]:
    modulus = _integer(modulus, "modulus", 2)
    a = _integer(a, "a") % modulus
    if gcd(a, modulus) != 1:
        raise ValueError("a and modulus must be coprime for reversible multiplication")
    return a, modulus


def _swap_basis_states(circuit: QuantumCircuit, left: int, right: int) -> None:
    """Swap two basis states exactly, restoring intermediate Gray-path states."""
    path = [left]
    for bit in range(circuit.num_qubits):
        if (left ^ right) & (1 << bit):
            path.append(path[-1] ^ (1 << bit))
    edges = list(zip(path, path[1:]))
    # Walk to the other endpoint, then undo all but the last adjacent swap.
    for start, end in edges + edges[-2::-1]:
        target = (start ^ end).bit_length() - 1
        controls = [q for q in range(circuit.num_qubits) if q != target]
        if not controls:
            circuit.x(target)
            continue
        control_state = sum(((start >> q) & 1) << i for i, q in enumerate(controls))
        circuit.append(MCXGate(len(controls), ctrl_state=control_state), controls + [target])


def _multiplication_gate(a: int, modulus: int, power: int, controlled: bool) -> Gate:
    a, modulus = _validate_modulus(a, modulus)
    power = _integer(power, "power", 0)
    multiplier = pow(a, power, modulus)
    width = (modulus - 1).bit_length()
    offset = int(controlled)
    prefix = "c_" if controlled else ""
    circuit = QuantumCircuit(width + offset, name=f"{prefix}mul_{multiplier}_mod_{modulus}")

    # x >= modulus is fixed. Coprimality makes the remaining map a bijection,
    # so this defines a unitary on the ENTIRE 2**width-dimensional space.
    visited: set[int] = set()
    for start in range(modulus):
        if start in visited:
            continue
        cycle = []
        current = start
        while current not in visited:
            visited.add(current)
            cycle.append(current)
            current = multiplier * current % modulus
        # (c0 c1 ... ck) = swaps (c0,c1), (c0,c2), ... in circuit time order.
        for end in cycle[1:]:
            _swap_basis_states(circuit, (start << offset) | offset, (end << offset) | offset)

    return circuit.to_gate()


def modular_multiplication(a: int, modulus: int, power: int = 1) -> Gate:
    """Return |x> -> |a**power * x mod modulus>, fixing x >= modulus.

    Qubit 0 is the least significant work bit. Uses ceil(log2(modulus))
    work qubits, no ancillas, and no precomputed order or factors. The constant
    pow(a, power, modulus) is computed first instead of repeating a circuit
    `power` times. Non-coprime multipliers are rejected.
    """
    return _multiplication_gate(a, modulus, power, controlled=False)


def controlled_modular_multiplication(a: int, modulus: int, power: int = 1) -> Gate:
    """As modular_multiplication, with a leading control qubit (active on 1).

    Append to [control, work[0], work[1], ...]. Work bits are little-endian.
    Control 0 acts as identity, including on unused states x >= modulus.
    """
    return _multiplication_gate(a, modulus, power, controlled=True)
