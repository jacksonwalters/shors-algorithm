"""General arithmetic QPE and an exact sparse simulation of its actual gates.

The sparse simulator evolves the reversible gate network on every counting
basis branch and then applies the inverse QFT by FFT. It never replaces the
network with pow(a, x, N), an orbit table, or a classically computed order.
This is an ideal simulation optimization, not a new quantum algorithm.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from time import perf_counter

import numpy as np
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
from qiskit.circuit.library import QFTGate

from .arithmetic import arithmetic_modular_multiplication
from .modular import _integer, _validate_modulus
from .order_finding import factors_from_counts, recover_periods


def arithmetic_modular_exponentiation(
    a: int, modulus: int, counting_qubits: int | None = None
) -> QuantumCircuit:
    """|j>|0>|0> -> |j>|a**j mod N>|0>, using binary arithmetic only.

    Layout: counting[t], work[n], scratch[2*n+3]. Includes initialization
    of the work to |1>, but no counting Hadamards, QFT, or measurement.
    """
    a, modulus = _validate_modulus(a, modulus)
    n = (modulus - 1).bit_length()
    t = 2 * n if counting_qubits is None else _integer(counting_qubits, "counting_qubits", 1)
    counting = QuantumRegister(t, "counting")
    work = QuantumRegister(n, "work")
    scratch = QuantumRegister(2 * n + 3, "scratch")
    circuit = QuantumCircuit(counting, work, scratch, name=f"arithmetic_modexp_{a}_{modulus}")
    circuit.x(work[0])
    # The first controlled multiply acts on the known value |1>. Prepare
    # |1> or |a> directly using their bitwise difference; no order is needed.
    for bit in range(n):
        if ((a ^ 1) >> bit) & 1:
            circuit.cx(counting[0], work[bit])
    multiplier = a * a % modulus
    gates = {}
    for control in counting[1:]:
        if multiplier != 1:
            if multiplier not in gates:
                gates[multiplier] = arithmetic_modular_multiplication(
                    multiplier, modulus, guard_invalid=False,
                )
            circuit.append(gates[multiplier], [control, *work, *scratch])
        multiplier = multiplier * multiplier % modulus
    circuit.metadata = {"implementation": "ripple_carry_arithmetic", "base": a,
                        "modulus": modulus, "counting_qubits": t, "work_qubits": n,
                        "scratch_qubits": 2 * n + 3,
                        "initial_multiply": "prepare_1_or_a",
                        "range_checks": "omitted_valid_residue_invariant"}
    return circuit


def arithmetic_order_finding_circuit(
    a: int, modulus: int, counting_qubits: int | None = None, *, measure: bool = True
) -> QuantumCircuit:
    modexp = arithmetic_modular_exponentiation(a, modulus, counting_qubits)
    circuit = QuantumCircuit(*modexp.qregs, name=f"arithmetic_order_{a}_{modulus}")
    counting = circuit.qregs[0]
    circuit.h(counting)
    circuit.compose(modexp, inplace=True)
    circuit.append(QFTGate(len(counting)).inverse(), counting)
    if measure:
        phase = ClassicalRegister(len(counting), "phase")
        circuit.add_register(phase)
        circuit.measure(counting, phase)
    circuit.metadata = modexp.metadata.copy()
    return circuit


def _reversible_operations(circuit, mapping=None):
    if float(circuit.global_phase) != 0:
        raise ValueError("sparse arithmetic simulation does not accept circuit phases")
    if mapping is None:
        mapping = list(range(circuit.num_qubits))
    positions = {bit: mapping[i] for i, bit in enumerate(circuit.qubits)}
    for instruction in circuit.data:
        name = instruction.operation.name
        args = tuple(positions[bit] for bit in instruction.qubits)
        if name in ("x", "cx", "ccx", "swap", "cswap"):
            yield name, args
        elif name in ("id", "barrier"):
            continue
        elif instruction.operation.definition is not None:
            yield from _reversible_operations(instruction.operation.definition, args)
        else:
            raise ValueError(f"unsupported operation for reversible simulation: {name}")


def evolve_basis_states(circuit: QuantumCircuit, basis_states: Iterable[int]) -> np.ndarray:
    """Apply every X/CX/CCX/SWAP in a reversible circuit to basis indices.

    This classical simulator is used for exhaustive arithmetic checks and
    sparse quantum simulation. Unsupported (including phase) gates raise an
    error. It does not inspect the modulus or the intended arithmetic map.
    """
    if circuit.num_qubits > 63:
        raise ValueError("the sparse simulator supports at most 63 total qubits")
    initial = np.asarray(list(basis_states))
    if initial.dtype.kind not in "iu" or initial.ndim != 1:
        raise ValueError("basis states must be a one-dimensional integer sequence")
    if np.any(initial < 0) or np.any(initial >= 1 << circuit.num_qubits):
        raise ValueError("basis index does not fit in this circuit")
    states = initial.astype(np.uint64, copy=True)
    for name, args in _reversible_operations(circuit):
        if name == "x":
            states ^= np.uint64(1 << args[0])
        elif name in ("cx", "ccx"):
            controls = np.uint64(sum(1 << bit for bit in args[:-1]))
            selected = (states & controls) == controls
            states[selected] ^= np.uint64(1 << args[-1])
        else:
            left, right = args[-2:]
            selected = ((states >> np.uint64(left)) ^ (states >> np.uint64(right))) & np.uint64(1)
            if name == "cswap":
                selected &= (states >> np.uint64(args[0])) & np.uint64(1)
            states[selected.astype(bool)] ^= np.uint64((1 << left) | (1 << right))
    return states


def arithmetic_phase_probabilities(a: int, modulus: int, counting_qubits: int | None = None) -> np.ndarray:
    """Exact ideal phase probabilities from gate evolution followed by an FFT.

    Only 2**t branches are populated before the inverse QFT, even though the
    full dense state has 2**(t+3*n+3) amplitudes. This avoids allocating tens
    or hundreds of GB for clean ancillas. Memory/time still grow exponentially
    with t: this simulation has no claim of quantum computational advantage.
    """
    modexp = arithmetic_modular_exponentiation(a, modulus, counting_qubits)
    t = modexp.metadata["counting_qubits"]
    n = modexp.metadata["work_qubits"]
    if t > 18:
        raise ValueError("the sparse demonstration is limited to 18 counting bits")
    dimension = 1 << t
    counting_values = np.arange(dimension, dtype=np.uint64)
    branches = evolve_basis_states(modexp, counting_values)
    if not np.array_equal(branches & np.uint64(dimension - 1), counting_values):
        raise AssertionError("arithmetic modified a counting-register bit")
    if np.any(branches >> np.uint64(t + n)):
        raise AssertionError("arithmetic did not return every scratch qubit to zero")
    work_values = branches >> np.uint64(t)
    probabilities = np.zeros(dimension)
    for work in np.unique(work_values):
        # Within each orthogonal work label, all branches interfere under
        # inverse QFT. Different work labels are traced out, not interfered.
        amplitudes = np.fft.fft((work_values == work).astype(float)) / dimension
        probabilities += np.abs(amplitudes) ** 2
    return probabilities / probabilities.sum()


@dataclass(frozen=True)
class ArithmeticSimulationResult:
    modulus: int
    base: int
    counting_qubits: int
    work_qubits: int
    scratch_qubits: int
    method: str
    counts: dict[str, int]
    periods: tuple[int, ...]
    factors: tuple[int, int] | None
    elapsed_seconds: float


def simulate_arithmetic(
    a: int, modulus: int, *, counting_qubits: int | None = None,
    shots: int = 2048, seed: int = 7, method: str = "sparse",
) -> ArithmeticSimulationResult:
    """One coprime-base run; methods: exact sparse gates or Qiskit Aer MPS.

    Aer is optional (`pip install -e '.[noise]'`). Its numerical SVD truncation
    threshold is 1e-16, with no imposed maximum bond dimension.
    Neither method uses IBM credentials or submits a job.
    """
    start = perf_counter()
    a, modulus = _validate_modulus(a, modulus)
    shots = _integer(shots, "shots", 1)
    circuit = arithmetic_order_finding_circuit(a, modulus, counting_qubits)
    t = circuit.num_clbits
    n = circuit.metadata["work_qubits"]
    if method == "sparse":
        probabilities = arithmetic_phase_probabilities(a, modulus, t)
        samples = np.random.default_rng(seed).multinomial(shots, probabilities)
        counts = {format(i, f"0{t}b"): int(count) for i, count in enumerate(samples) if count}
    elif method == "aer-mps":
        from qiskit_aer import AerSimulator
        backend = AerSimulator(method="matrix_product_state",
                               matrix_product_state_truncation_threshold=1e-16,
                               max_parallel_threads=4)
        compiled = transpile(circuit, backend, optimization_level=0)
        result = backend.run(compiled, shots=shots, seed_simulator=seed).result()
        counts = result.get_counts()
    else:
        raise ValueError("method must be 'sparse' or 'aer-mps'")
    return ArithmeticSimulationResult(
        modulus, a, t, n, circuit.metadata["scratch_qubits"], method, counts,
        recover_periods(counts, a, modulus, t),
        factors_from_counts(counts, a, modulus, t), perf_counter() - start,
    )
