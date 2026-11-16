"""Small, explicitly compiled Shor demonstrations for IBM hardware.

These are instance-specific circuits for base 2, not scalable arithmetic.
The 15 circuit keeps the ordinary binary work register. The 21 circuit uses
a known encoding of its six reachable residues. See WORK_ENCODING_21 below.
"""

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit.library import QFTGate

from .modular import _integer


# A fixed isometry from ordinary residues to three work qubits, including
# phases. The relative-phase Toffoli pair cycles 1 -> 2 -> -i*3 -> 1 on a
# two-qubit trit. Tensoring with a parity flip gives a six-state cycle.
# This encoding is CLASSICALLY PRECOMPILED and contains order information.
# Each value is (little-endian basis index, amplitude).
WORK_ENCODING_21 = {
    1: (2, 1),
    2: (5, 1),
    4: (6, -1j),
    8: (3, 1),
    16: (4, 1),
    11: (7, -1j),
}


def compiled_modular_exponentiation(modulus: int, counting_qubits: int) -> QuantumCircuit:
    """Map |x>|0> to |x>E|2**x mod N>, including work initialization.

    Correct on the initialized work subspace, not an arbitrary-work
    multiplication oracle. For N=15, E is the ordinary binary encoding.
    For N=21, E is WORK_ENCODING_21. No measurements or Hadamards are added.
    """
    modulus = _integer(modulus, "modulus", 2)
    if modulus not in (15, 21):
        raise ValueError("compiled hardware demonstrations support only 15 and 21")
    counting_qubits = _integer(counting_qubits, "counting_qubits", 2)
    counting = QuantumRegister(counting_qubits, "counting")
    work = QuantumRegister(4 if modulus == 15 else 3, "work")
    circuit = QuantumCircuit(counting, work, name=f"compiled_modexp_2_mod_{modulus}")
    if modulus == 15:
        circuit.x(work[0])
        # With work initially |1>, the first multiplication only selects
        # between |1> and |2>; its three controlled swaps reduce to two CXs.
        circuit.cx(counting[0], work[0])
        circuit.cx(counting[0], work[1])
        circuit.cswap(counting[1], work[0], work[2])
        circuit.cswap(counting[1], work[1], work[3])
        # 2**(2**j) mod 15 = 1 for j >= 2.
    else:
        parity, low, high = work
        circuit.x(low)
        # First controlled step acts on a known basis state and has phase +1.
        circuit.cx(counting[0], parity)
        circuit.cx(counting[0], low)
        circuit.cx(counting[0], high)
        for j in range(1, counting_qubits):
            # V = RCCX(c,l,h); RCCX(c,h,l), with V**3 = I EXACTLY.
            # V**2 = V.inverse(), obtained by reversing the pair. The pair's
            # phases must be retained consistently; replacing unrelated CCXs
            # with RCCXs is not generally safe for phase estimation.
            first, second = (low, high) if j % 2 == 0 else (high, low)
            circuit.rccx(counting[j], first, second)
            circuit.rccx(counting[j], second, first)
    return circuit


def compiled_order_finding_circuit(
    modulus: int, counting_qubits: int | None = None, *, measure: bool = True
) -> QuantumCircuit:
    """QPE for the compiled base-2 demonstrations, with a `phase` register.

    Defaults: N=15 uses 4 counting + 4 binary work qubits; N=21 uses 5
    counting + 3 encoded work qubits. Extra counting bits distinguish the
    ideal phase distribution from uniform noise even for period 4.
    """
    if counting_qubits is None:
        counting_qubits = 4 if modulus == 15 else 5
    modexp = compiled_modular_exponentiation(modulus, counting_qubits)
    circuit = QuantumCircuit(*modexp.qregs, name=f"compiled_shor_{modulus}")
    counting = circuit.qregs[0]
    circuit.h(counting)
    circuit.compose(modexp, inplace=True)
    circuit.append(QFTGate(counting_qubits).inverse(), counting)
    if measure:
        phase = ClassicalRegister(counting_qubits, "phase")
        circuit.add_register(phase)
        circuit.measure(counting, phase)
    circuit.metadata = {
        "modulus": modulus,
        "base": 2,
        "counting_qubits": counting_qubits,
        "implementation": "compiled_binary" if modulus == 15 else "compiled_encoded_orbit",
    }
    return circuit
