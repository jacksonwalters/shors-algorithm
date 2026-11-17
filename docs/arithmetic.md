# General reversible arithmetic

The arithmetic builder receives `a`, `N`, and the desired phase precision.
It never enumerates residues or computes the multiplicative order. Its
classical arithmetic consists of constant reduction, repeated squaring, GCD
validation, and the modular inverse of `a` (extended Euclid). The existing
permutation reference and compact hardware demonstrations remain separate.

## Constant addition with a carry chain

`constant_adder(k, w, controlled=False)` uses a `w`-bit value register and
`w-1` initially zero carry qubits. An optional leading control enables the
addition. Registers are little-endian.

For each bit, with incoming carry `c_i` and the selected constant bit `k_i`,

```text
c_(i+1) = majority(x_i, k_i, c_i)
y_i     = x_i XOR k_i XOR c_i
```

For controlled addition, `k_i` is either zero or the control bit. Majority
is computed as `x XOR ((x XOR y) AND (x XOR z))`, temporarily XORing `x`
into the other two inputs and restoring them afterward. This uses one CCX
and five CX gates instead of three CCXs. The identity holds for every input,
including a dirty output bit. Only X, CX, and exact CCX gates are needed.
After changing the sum bits, the old carry is also
`majority(NOT y_i, k_i, c_i)`. Applying this in reverse bit order erases the
carry chain without changing the sum. The result is addition modulo `2**w`;
negative constants use the inverse circuit. Trailing zero constant bits need
no carry operations.

Construction iterates over bits, not over the `2**w` possible input values.
Gate count and carry storage are linear in `w`.

## Addition modulo an arbitrary N

Let `n = ceil(log2(N))`. `modular_adder(k, N)` uses this register layout:

```text
[control?] | value[n] | overflow[1] | carries[n] | borrow[1]
```

All scratch bits start at zero. Its arithmetic/cleanup contract requires
`0 <= value < N`, with `k` reduced modulo `N`. The extra high bit makes the
sign of a temporary subtraction available without classical measurement.

The circuit adds `k`, subtracts `N`, records underflow in the borrow flag,
and conditionally adds `N` back. To clean the borrow flag, it temporarily
subtracts `k`, toggles the flag with the complement of the sign bit, then
adds `k` again. In the controlled variant, the `k` operations depend on the
external control; the `N` operations and borrow cleanup cancel even when the
control is zero. The result lies in `[0, N)` and every scratch bit is zero.

This primitive is a unitary on the entire register, but it does not promise
modular addition or clean scratch for an out-of-range value. The in-place
multiplier below explicitly guards such inputs.

## Multiplication and cleanup

`multiply_accumulate(a, N)` performs

```text
|control, x, y, 0...0> -> |control, x, (y + control*a*x) mod N, 0...0>
```

for `y < N`, with any `n`-bit `x`. Each source bit controls addition of the
known constant `a*2**j mod N`. An enable qubit combines the external control
and the current source bit, then is uncomputed. Coprimality is unnecessary
for this accumulation because it preserves `x`.

For in-place multiplication, coprimality is required. The public gate
`arithmetic_modular_multiplication(a, N, power=1)` uses:

```text
control[1] | work[n] | accumulator[n] | overflow[1] | carries[n]
           | borrow[1] | active[1] | enable[1]
```

All `2*n+4` scratch bits start at zero. It implements:

1. Compute `active = control AND (work < N)` using a temporary subtraction.
2. Accumulate `a*work mod N` into the zero accumulator, controlled by active.
3. Swap work and accumulator, controlled by active.
4. Invert the accumulation for `a_inverse mod N`. The accumulator becomes
   `old_work - a_inverse*new_work mod N = 0`.
5. Uncompute active. Multiplication preserved the valid/invalid predicate.

This gives the desired modular multiplication on valid residues and identity
on control 0 or work values `>= N`, always returning the scratch to zero.
The action on an arbitrary dirty scratch input is unspecified, but the gate
remains unitary there. No relative-phase Toffoli substitutions are made.

The optional `guard_invalid=False` mode requires `work < N`, omits both
range checks and the active flag, and controls accumulation/swaps directly.
It uses `2*n+3` scratch qubits and `3*n+4` qubits overall. It remains unitary
everywhere, but its arithmetic and scratch-cleanup contract applies only
to valid work values. The default guarded public gate still fixes unused
states. Tests exhaustively check both modes on their promised inputs.

A controlled multiplier uses `3*n+5` qubits and `O(n²)` X/CX/CCX/CSWAP gates.
Each of those gates has a constant-size decomposition into one- and two-qubit
gates. With `t` counting bits, optimized QPE uses `t+3*n+3` qubits and
`O(t*n² + t²)` gates; at `t=2*n`, these become `5*n+3` and `O(n³)`.
These are ideal gate bounds, not routing or fault-tolerant resource estimates.

## Phase estimation and simulation

`arithmetic_order_finding_circuit(a, N, counting_qubits=None)` initializes
work to binary `|1>`. The first controlled multiply acts on a known value,
so CNOTs on the differing bits of `1` and `a` prepare `|1>` or `|a>` directly.
Subsequent controlled powers are computed by repeated squaring. Work starts
valid and multiplication preserves that invariant, so those multipliers
omit range checks. Neither simplification needs the order or factors.
The circuit ends with the complete inverse QFT. The measured classical
register is named `phase`, consistent with the rest of the repository.

Two independent ideal simulation paths are available:

- **Qiskit Aer matrix product state:** executes the complete Qiskit circuit.
  The SVD truncation threshold is `1e-16`, with no maximum bond dimension.
  Results for 15, 21, 33, and 35 were saved from this path.
- **Sparse gate-level simulation:** starts from all `2**t` counting branches,
  executes every reversible gate on the corresponding basis indices, and
  applies the inverse QFT by FFT within each final work label. It verifies
  that counting bits were preserved and all scratch bits are zero. It rejects
  phase gates rather than treating them as classical permutations. It never
  uses `pow(a, exponent, N)` to replace circuit evolution or searches for an
  order. Exponentially many counting branches are still simulated.

For 35 at default precision there are 33 total qubits. A dense double-complex
statevector would occupy 128 GiB, while only 4,096 basis branches are populated
before the inverse QFT. Sparsity and MPS make this small demonstration practical
to simulate; neither establishes a classical or quantum factoring advantage.

Classical post-processing is shared with the existing implementation:
continued-fraction candidates, LCMs of reduced denominators, modular period
verification, and nontrivial GCD extraction. Prime/perfect-power preprocessing
and automatic base retries are outside this one-base experiment API.

## Validation and hardware limits

Tests cover all modular addends and valid inputs for several moduli; every
coprime multiplier for 15, 21, 33, 35 and other small moduli; control-off and
unused states; nonzero multiply-accumulate inputs; modular powers; arbitrary
complex superpositions in Qiskit; full phase distributions; independent Aer
sampling; and failure cases. Classical formulas and known orders appear only
as independent test oracles, never in the arithmetic circuit builder.

The [initial experiment report](../results/arithmetic_2026-11-16/REPORT.md)
records the baseline before the final optimizations above. The
[bounded final assessment](../results/final_35_2026-11-16/REPORT.md) compares
the optimized 35 circuit at 6 and 12 counting bits on IBM Fez. It includes
calibrated gate-error and timing diagnostics, with their limitations. No
general-arithmetic hardware job was submitted. The project stops at 35;
larger instances and further arithmetic architectures are outside its scope.

References: [Vedral–Barenco–Ekert arithmetic networks](https://arxiv.org/abs/quant-ph/9511018)
and [Beauregard's alternative 2n+3-qubit construction](https://arxiv.org/abs/quant-ph/0205095).
