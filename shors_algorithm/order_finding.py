"""Phase estimation and checked classical post-processing for small Shor demos."""

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from math import gcd, lcm

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
from qiskit.circuit.library import QFTGate
from qiskit.primitives import StatevectorSampler

from .modular import _integer, _validate_modulus, controlled_modular_multiplication


def order_finding_circuit(
    a: int, modulus: int, counting_qubits: int | None = None, *, measure: bool = True
) -> QuantumCircuit:
    """Build QPE for multiplication by a mod modulus, starting the work at |1>.

    Defaults to 2*ceil(log2(modulus)) counting qubits. Both quantum registers
    are little-endian; the measured integer is int(bitstring, 2). The classical
    register is named `phase`, for both local and IBM SamplerV2 results.
    """
    a, modulus = _validate_modulus(a, modulus)
    width = (modulus - 1).bit_length()
    if counting_qubits is None:
        counting_qubits = 2 * width
    counting_qubits = _integer(counting_qubits, "counting_qubits", 1)
    counting = QuantumRegister(counting_qubits, "counting")
    work = QuantumRegister(width, "work")
    circuit = QuantumCircuit(counting, work, name=f"order_{a}_mod_{modulus}")
    circuit.h(counting)
    circuit.x(work[0])

    gates = {}
    multiplier = a
    for control in counting:
        if multiplier != 1:
            if multiplier not in gates:
                gates[multiplier] = controlled_modular_multiplication(multiplier, modulus)
            circuit.append(gates[multiplier], [control, *work])
        # a**(2**j) mod N, computed by repeated squaring, never a huge integer.
        multiplier = multiplier * multiplier % modulus

    circuit.append(QFTGate(counting_qubits).inverse(), counting)
    if measure:
        phase = ClassicalRegister(counting_qubits, "phase")
        circuit.add_register(phase)
        circuit.measure(counting, phase)
    return circuit


def _convergents(numerator: int, denominator: int):
    """Yield exact continued-fraction convergents, without float rounding."""
    p_prev, p = 0, 1
    q_prev, q = 1, 0
    while denominator:
        quotient, remainder = divmod(numerator, denominator)
        p_prev, p = p, quotient * p + p_prev
        q_prev, q = q, quotient * q + q_prev
        yield Fraction(p, q)
        numerator, denominator = denominator, remainder


def _phase_denominators(measured: int, counting_qubits: int, modulus: int) -> set[int]:
    if measured == 0:
        return set()
    resolution = 1 << counting_qubits
    phase = Fraction(measured, resolution)
    return {
        fraction.denominator
        for fraction in _convergents(measured, resolution)
        if 1 < fraction.denominator < modulus
        and abs(phase - fraction) <= Fraction(1, resolution)
    }


def recover_periods(
    counts: Mapping[str, int], a: int, modulus: int, counting_qubits: int
) -> tuple[int, ...]:
    """Recover verified periods from measured phases and their denominator LCMs.

    s/r may reduce to a smaller denominator, so combine evidence across shots
    (e.g. denominators 2 and 3 yield 6). Do not enumerate multiples of a guess
    or classically search for the order. Return only r < modulus with a**r = 1
    mod modulus. A verified period can be a multiple of the minimal order.
    Noise may also produce such candidates: this is not a fidelity estimate.
    """
    a, modulus = _validate_modulus(a, modulus)
    counting_qubits = _integer(counting_qubits, "counting_qubits", 1)
    denominators = set()
    for bitstring, count in counts.items():
        count = _integer(count, "count", 0)
        if (
            not isinstance(bitstring, str)
            or len(bitstring) != counting_qubits
            or set(bitstring) - {"0", "1"}
        ):
            raise ValueError("counts keys must be binary strings of length counting_qubits")
        if count:
            denominators.update(_phase_denominators(int(bitstring, 2), counting_qubits, modulus))

    candidates: set[int] = set()
    for denominator in sorted(denominators):
        combinations = {lcm(previous, denominator) for previous in candidates}
        candidates.add(denominator)
        candidates.update(period for period in combinations if period < modulus)
    return tuple(sorted(period for period in candidates if pow(a, period, modulus) == 1))


def factors_from_period(a: int, modulus: int, period: int) -> tuple[int, int] | None:
    """Extract a nontrivial divisor pair from a verified even period, if possible."""
    a, modulus = _validate_modulus(a, modulus)
    period = _integer(period, "period", 1)
    if period % 2 or pow(a, period, modulus) != 1:
        return None
    halfway = pow(a, period // 2, modulus)
    if halfway in (1, modulus - 1):
        return None
    for sign in (-1, 1):
        divisor = gcd(halfway + sign, modulus)
        if 1 < divisor < modulus:
            return tuple(sorted((divisor, modulus // divisor)))
    return None


def factors_from_counts(
    counts: Mapping[str, int], a: int, modulus: int, counting_qubits: int
) -> tuple[int, int] | None:
    """Return checked factors, or None when these samples/base are unhelpful."""
    for period in recover_periods(counts, a, modulus, counting_qubits):
        factors = factors_from_period(a, modulus, period)
        if factors is not None:
            return factors
    return None


@dataclass(frozen=True)
class SimulationResult:
    modulus: int
    base: int
    counting_qubits: int
    work_qubits: int
    counts: dict[str, int]
    periods: tuple[int, ...]
    factors: tuple[int, int] | None


def simulate(
    a: int,
    modulus: int,
    *,
    counting_qubits: int | None = None,
    shots: int = 2048,
    seed: int | None = 7,
) -> SimulationResult:
    """Run one coprime-base order-finding experiment locally, without credentials.

    This is a small-instance demonstration, not a complete recursive factoring
    driver: primality/perfect-power checks and retries with other bases belong
    to the caller. None means more samples or a different base may be needed.
    """
    shots = _integer(shots, "shots", 1)
    a, modulus = _validate_modulus(a, modulus)
    circuit = order_finding_circuit(a, modulus, counting_qubits)
    counting_qubits = circuit.num_clbits
    sampler = StatevectorSampler(seed=seed)
    counts = sampler.run([circuit], shots=shots).result()[0].data.phase.get_counts()
    periods = recover_periods(counts, a, modulus, counting_qubits)
    factors = next(
        (pair for period in periods if (pair := factors_from_period(a, modulus, period)) is not None),
        None,
    )
    return SimulationResult(
        modulus, a, counting_qubits, (modulus - 1).bit_length(), counts, periods, factors
    )
