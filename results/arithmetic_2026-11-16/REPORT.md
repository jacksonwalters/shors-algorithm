# General arithmetic factoring: simulation and resource report

**Historical baseline, before the final optimization round.** The saved
counts, source hashes, and resource values below describe that earlier
implementation. Current commands build the optimized circuit and will have
different resource counts. The [final assessment](../final_35_2026-11-16/REPORT.md)
records the bounded conclusion at 35 and supersedes the proposed next steps.

The same reversible arithmetic builder factored **15, 21, 33, and 35** in Qiskit Aer. It receives the base and modulus, constructs ripple-carry arithmetic, and receives no orders, orbit tables, or factors. This report concerns **ideal local simulations**, separate from the earlier compact IBM hardware demonstrations.

## Observed results

Each run used 2,048 shots, seed 7, and `2*ceil(log2(N))` counting bits. Aer used matrix product states, an SVD truncation threshold of `1e-16`, and no imposed maximum bond dimension.

| N | Base | Period(s) recovered | Factors | Counting / work / scratch | Total qubits | CX count before routing |
| --- | ---: | --- | --- | --- | ---: | ---: |
| 15 | 2 | [4] | 3 × 5 | 8 / 4 / 12 | 24 | 5,904 |
| 21 | 2 | [6] | 3 × 7 | 10 / 5 / 14 | 29 | 41,025 |
| 33 | 5 | [10] | 3 × 11 | 12 / 6 / 16 | 34 | 73,746 |
| 35 | 2 | [12] | 5 × 7 | 12 / 6 / 16 | 34 | 78,603 |

All-to-all decomposition used Qiskit 2.6.2, the `u`/`cx` basis, optimization level 1, and seed 7. The saved records include software versions, source hashes, measured counts, elapsed times, and resources. Times describe single local runs, not controlled performance benchmarks.

## Independent simulation checks

The sparse simulator executes every reversible gate on all counting branches, checks the counting register and scratch cleanup, then applies the inverse QFT by FFT. It does not replace the gate network with `pow(a, exponent, N)` or determine an order classically. Aer independently executes the full Qiskit circuit.

| N | Aer vs sparse total variation | Classical distribution fidelity |
| --- | ---: | ---: |
| 15 | 0.00977 | 0.99988 |
| 21 | 0.05296 | 0.97355 |
| 33 | 0.06250 | 0.96451 |
| 35 | 0.08473 | 0.95555 |

These sampled distributions differ because of finite shots. The tests additionally compare complete exact sparse phase probabilities to independent Fourier calculations, and small full circuits to Qiskit dense statevectors. Known orders and integer modular exponentiation are used as independent test oracles only.

For the 35 circuit, a dense 34-qubit double-complex statevector would require 256 GiB. The pre-QFT state has only 4,096 occupied branches. Sparse simulation and Aer MPS avoid this dense allocation. Neither simulation demonstrates a factoring speedup.

## Actual device compilation, without submission

The general 35 circuit was compiled against **ibm_fez** using live target data, optimization level 1, and seed 7. The returned calibration timestamp was `2026-11-13 11:27:59-05:00`.

- Logical qubits: **34**; active physical qubits after routing: **34**.
- Native CZ gates: **213,936**.
- Two-qubit depth: **148,390**.
- Total circuit depth: **497,547**.
- **No general-arithmetic hardware job was submitted.**

This is a compilation measurement, not a hardware success estimate or noise simulation. Its depth is far beyond the few-dozen-gate compiled demonstrations already run on IBM Fez. A subsequent bounded optimization and calibration assessment is recorded in the final report linked above; no general-arithmetic hardware experiment followed.

## Implementation and tests

The multiplier uses `3*n+5` qubits including its control and `O(n²)` ideal elementary gates. Standard QPE with `2*n` counting bits uses `5*n+4` qubits and `O(n³)` gates. Unlike the previous permutation synthesis, circuit generation iterates over bits rather than enumerating residues. The arithmetic has a polynomial resource bound but is not yet optimized for practical noisy hardware.

The complete suite has **299 passing tests**: 145 existing tests and 154 arithmetic tests. New tests exercise every addend/input for several moduli; every coprime base for 15, 21, 33, 35 and other small moduli; control-off and invalid work states; clean carry/borrow/accumulator registers; powers; complex superpositions; phase distributions; multiple factoring bases; and independent Aer sampling.

See [design notes](../../docs/arithmetic.md) for register layouts and the cleanup construction.

## Reproduce

From the repository root, after installing the `dev` and `noise` extras:

```sh
python -m shors_algorithm.arithmetic_experiment --number 15 --base 2 --method aer-mps --resources
python -m shors_algorithm.arithmetic_experiment --number 21 --base 2 --method aer-mps --resources
python -m shors_algorithm.arithmetic_experiment --number 33 --base 5 --method aer-mps --resources
python -m shors_algorithm.arithmetic_experiment --number 35 --base 2 --method aer-mps --resources
python -m shors_algorithm.arithmetic_experiment --number 35 --base 2 --backend ibm_fez
python -m pytest -q
```

The last experiment command reads IBM calibration data and compiles only; it never submits a job. It requires the existing saved IBM account. The other commands run locally. Pass `--output path.json` to save a new record; use a new filename to preserve these observed results.

## Saved artifacts

- [N15_a2_aer_mps.json](N15_a2_aer_mps.json): independent Aer run and raw counts.
- [N21_a2_aer_mps.json](N21_a2_aer_mps.json): independent Aer run and raw counts.
- [N33_a5_aer_mps.json](N33_a5_aer_mps.json): independent Aer run and raw counts.
- [N35_a2_aer_mps.json](N35_a2_aer_mps.json): independent Aer run and raw counts.
- [N35_a2_sparse.json](N35_a2_sparse.json): sparse run, all-to-all and IBM Fez compilation metrics, and physical layouts.
- [simulator_comparison.json](simulator_comparison.json): sampled Aer distribution comparisons.
