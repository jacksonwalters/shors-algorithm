"""Polynomial-size reversible binary arithmetic, without residue/orbit tables.

Little-endian registers throughout. Constant addition computes carries,
changes the sum bits, then uncomputes carries from the new sum. All gates are
exact X, CX, CCX, or controlled SWAP: no relative-phase approximations.

For n-bit N, a controlled in-place multiplier uses 3*n+5 qubits and O(n**2)
elementary gates; QPE with O(n) counting bits uses O(n**3) gates. This favors
simple, testable ripple arithmetic over the smallest possible ancilla count.
"""

from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit import Gate

from .modular import _integer, _validate_modulus


def _xor_carry(circuit, bit, carry_in, carry_out, constant_bit, control):
    """XOR majority(bit, constant_bit * control, carry_in) into carry_out."""
    if not constant_bit:
        if carry_in is not None:
            circuit.ccx(bit, carry_in, carry_out)
    elif control is None:
        # majority(bit, 1, carry_in) = bit OR carry_in.
        circuit.cx(bit, carry_out)
        if carry_in is not None:
            circuit.cx(carry_in, carry_out)
            circuit.ccx(bit, carry_in, carry_out)
    else:
        if carry_in is None:
            circuit.ccx(bit, control, carry_out)
        else:
            # majority(x, y, z) = x XOR ((x XOR y) AND (x XOR z)).
            # Restore both temporary XORs: one exact CCX and five CXs
            # replace three CCXs, with no relative phases or input promises.
            circuit.cx(bit, control)
            circuit.cx(bit, carry_in)
            circuit.ccx(control, carry_in, carry_out)
            circuit.cx(bit, carry_out)
            circuit.cx(bit, carry_in)
            circuit.cx(bit, control)


def constant_adder(constant: int, num_bits: int, *, controlled: bool = False) -> QuantumCircuit:
    """Add a signed classical constant modulo 2**num_bits, with clean carries.

    Layout: [control?], value[num_bits], carries[num_bits-1]. Carries must
    start at zero and return to zero. Control 0 is identity. A negative
    constant uses the inverse of the corresponding positive-constant circuit.
    No register containing the classical constant is needed.
    """
    constant = _integer(constant, "constant")
    num_bits = _integer(num_bits, "num_bits", 1)
    offset = int(controlled)
    circuit = QuantumCircuit(2 * num_bits - 1 + offset, name=f"add_{constant}_{num_bits}")
    value = list(range(offset, offset + num_bits))
    carries = list(range(offset + num_bits, circuit.num_qubits))
    control = 0 if controlled else None
    amount = abs(constant) % (1 << num_bits)
    if not amount:
        return circuit
    first = (amount & -amount).bit_length() - 1
    for i in range(first, num_bits - 1):
        carry_in = carries[i - 1] if i > first else None
        _xor_carry(circuit, value[i], carry_in, carries[i], (amount >> i) & 1, control)
    for i in range(first, num_bits):
        if (amount >> i) & 1:
            if control is None:
                circuit.x(value[i])
            else:
                circuit.cx(control, value[i])
        if i > first:
            circuit.cx(carries[i - 1], value[i])
    # If y_i = x_i XOR a_i XOR carry_i, the same carry-out is
    # majority(NOT y_i, a_i, carry_i). Erase from high to low.
    for i in reversed(range(first, num_bits - 1)):
        carry_in = carries[i - 1] if i > first else None
        circuit.x(value[i])
        _xor_carry(circuit, value[i], carry_in, carries[i], (amount >> i) & 1, control)
        circuit.x(value[i])
    return circuit.inverse() if constant < 0 else circuit


def modular_adder(constant: int, modulus: int, *, controlled: bool = False) -> QuantumCircuit:
    """Add constant modulo N for value < N, restoring all scratch bits.

    Layout: [control?], value[n], overflow[1], carries[n], borrow[1], where
    n = ceil(log2(N)). All n+2 scratch bits must start at zero. The circuit
    is unitary everywhere, but this primitive's arithmetic/cleanup contract
    is for value < N. The in-place multiplier guards unused states separately.
    """
    modulus = _integer(modulus, "modulus", 2)
    constant = _integer(constant, "constant") % modulus
    n = (modulus - 1).bit_length()
    offset = int(controlled)
    circuit = QuantumCircuit(2 * n + 2 + offset, name=f"add_{constant}_mod_{modulus}")
    value = list(range(offset, offset + n + 1))  # Includes high overflow bit.
    carries = list(range(offset + n + 1, offset + 2 * n + 1))
    borrow = circuit.num_qubits - 1
    controlled_args = ([0] if controlled else []) + value + carries
    if constant == 0:
        return circuit
    add = constant_adder(constant, n + 1, controlled=controlled)
    subtract_modulus = constant_adder(-modulus, n + 1)
    restore_modulus = constant_adder(modulus, n + 1, controlled=True)
    circuit.compose(add, controlled_args, inplace=True)
    circuit.compose(subtract_modulus, value + carries, inplace=True)
    circuit.cx(value[-1], borrow)
    circuit.compose(restore_modulus, [borrow] + value + carries, inplace=True)
    circuit.compose(add.inverse(), controlled_args, inplace=True)
    circuit.x(value[-1])
    circuit.cx(value[-1], borrow)
    circuit.x(value[-1])
    circuit.compose(add, controlled_args, inplace=True)
    return circuit


def multiply_accumulate(a: int, modulus: int) -> QuantumCircuit:
    """Controlled |x>|y> -> |x>|y + a*x mod N>, for y < N and any n-bit x.

    Layout: control[1], x[n], accumulator[n], overflow[1], carries[n],
    borrow[1], enable[1]. Scratch starts and finishes at zero. Coprimality
    is not required for this out-of-place, reversible accumulation.
    """
    modulus = _integer(modulus, "modulus", 2)
    a = _integer(a, "a") % modulus
    n = (modulus - 1).bit_length()
    control = QuantumRegister(1, "control")
    source = QuantumRegister(n, "source")
    accumulator = QuantumRegister(n, "accumulator")
    overflow = QuantumRegister(1, "overflow")
    carries = QuantumRegister(n, "carry")
    borrow = QuantumRegister(1, "borrow")
    enable = QuantumRegister(1, "enable")
    circuit = QuantumCircuit(control, source, accumulator, overflow, carries, borrow, enable,
                             name=f"accumulate_{a}_mod_{modulus}")
    constant = a
    for bit in source:
        if constant:
            circuit.ccx(control[0], bit, enable[0])
            circuit.compose(modular_adder(constant, modulus, controlled=True),
                            [enable[0], *accumulator, *overflow, *carries, *borrow], inplace=True)
            circuit.ccx(control[0], bit, enable[0])
        constant = 2 * constant % modulus
    return circuit


def arithmetic_modular_multiplication(
    a: int, modulus: int, power: int = 1, *, guard_invalid: bool = True,
) -> Gate:
    """Controlled in-place multiplication, generated solely from a, N, power.

    Layout: control[1], work[n], accumulator[n], overflow[1], carries[n],
    borrow[1], active[1], enable[1]. All 2*n+4 scratch qubits start at zero
    and return to zero. Control 0 and work >= N act as identity. The control
    is qubit 0; the work register is ordinary little-endian binary.

    If guard_invalid=False, work must be < N. The active flag and range
    checks are omitted, reducing scratch to 2*n+3 and total width to 3*n+4.
    The gate remains unitary, but no arithmetic/cleanup promise is made for
    out-of-range inputs in that mode. QPE preserves the valid-input invariant.
    """
    a, modulus = _validate_modulus(a, modulus)
    power = _integer(power, "power", 0)
    a = pow(a, power, modulus)
    n = (modulus - 1).bit_length()
    control = QuantumRegister(1, "control")
    work = QuantumRegister(n, "work")
    accumulator = QuantumRegister(n, "accumulator")
    overflow = QuantumRegister(1, "overflow")
    carries = QuantumRegister(n, "carry")
    borrow = QuantumRegister(1, "borrow")
    active = QuantumRegister(1, "active") if guard_invalid else None
    enable = QuantumRegister(1, "enable")
    registers = [control, work, accumulator, overflow, carries, borrow]
    if active is not None:
        registers.append(active)
    circuit = QuantumCircuit(*registers, enable,
                             name=f"arithmetic_mul_{a}_mod_{modulus}")
    if a == 1:
        return circuit.to_gate()

    def toggle_active():
        # active ^= control AND (work < N), using a temporary subtraction.
        args = [control[0], *work, *overflow, *carries]
        circuit.compose(constant_adder(-modulus, n + 1, controlled=True), args, inplace=True)
        circuit.cx(overflow[0], active[0])
        circuit.compose(constant_adder(modulus, n + 1, controlled=True), args, inplace=True)

    if guard_invalid:
        toggle_active()
    selected = active[0] if guard_invalid else control[0]
    args = [selected, *work, *accumulator, *overflow, *carries, *borrow, *enable]
    circuit.compose(multiply_accumulate(a, modulus), args, inplace=True)
    for source, target in zip(work, accumulator):
        circuit.cswap(selected, source, target)
    # After the swap: accumulator holds the original x, work holds a*x mod N.
    # Subtract a^{-1}*work mod N to erase x. Inversion uses extended GCD,
    # not an order search or knowledge of the factors.
    circuit.compose(multiply_accumulate(pow(a, -1, modulus), modulus).inverse(), args, inplace=True)
    if guard_invalid:
        toggle_active()  # The valid/invalid predicate is unchanged by multiplication.
    return circuit.to_gate()
