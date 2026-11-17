# Final bounded result: 35

**35 = 5 × 7 was recovered in ideal Qiskit Aer simulation using general
reversible arithmetic. The hardware feasibility check did not justify a
QPU experiment, and no 35 hardware job was submitted. This concludes the
project at 35.** The earlier compiled demonstrations of 15 and 21 on IBM
Fez remain successful hardware results.

This was one focused optimization round, with no new arithmetic architecture,
larger factoring target, known-order encoding, or factor supplied to the builder.
The assessment ran on November 16, 2026 in America/New_York; JSON timestamps
use UTC (November 17). IBM returned calibration time
`2026-11-13 11:27:59-05:00` for every candidate.

## What changed

- Carry majority logic uses one exact Toffoli and five CNOTs in place of
  three Toffolis, restoring all temporarily changed inputs.
- The first controlled multiplication starts with known work value `1`,
  so CNOTs prepare `1` or `a` directly from the first counting bit.
- Subsequent multipliers omit range checks: work starts below `N` and
  multiplication by a coprime base preserves that invariant. This saves
  one scratch qubit. The standalone multiplier still guards unused states
  by default.
- Routing compared optimization level 1, seed 7, and level 3, seeds 7 and
  17. Selection minimized the existing calibration-error cost, followed
  by two-qubit count and depth. No candidates were run on hardware.

All arithmetic gates remain exact X, CX, CCX, and controlled SWAP gates.
No relative-phase substitution, orbit table, or order search was introduced.

## Ideal simulation

Both runs use base 2, 2,048 shots, seed 7, Qiskit 2.6.2 and Aer 0.18.2.
Aer uses matrix product states with SVD truncation threshold `1e-16` and
no maximum bond dimension. The independent sparse simulator executes the
actual reversible network and then the inverse QFT using FFTs.

| Counting bits | Counting / work / scratch | Verified period candidates | Factors | Aer vs exact sparse TVD | Distribution fidelity |
| ---: | --- | --- | --- | ---: | ---: |
| 6 | 6 / 6 / 15 | 12, 24 | 5 × 7 | 0.03986 | 0.99253 |
| 12 | 12 / 6 / 15 | 12 | 5 × 7 | 0.06823 | 0.96021 |

Period 24 is a verified multiple of the order; factor extraction uses the
useful candidate 12. Six counting bits deliberately trade phase resolution
for depth and do not provide the usual `2*n` precision guarantee. This
experiment setting was chosen before sampling, without using the order to
construct the circuit. The full 12-bit experiment retains default precision.
Finite-shot histograms are compared to exact probabilities, not to another
sampled histogram. These are simulator results, not quantum advantage claims.

## Resource comparison

| Circuit | Logical qubits | All-to-all CX | Fez native CZ | Fez two-qubit depth |
| --- | ---: | ---: | ---: | ---: |
| Initial 12-bit baseline | 34 | 78,603 | 213,936 | 148,390 |
| Optimized 12-bit, level 1 / seed 7 | 33 | 56,823 | 162,669 | 113,002 |
| Optimized 12-bit, selected level 3 / seed 7 | 33 | 56,823 | 139,161 | 96,504 |
| Optimized 6-bit, selected level 3 / seed 7 | 27 | 25,488 | 60,292 | 41,761 |

All-to-all decomposition uses `u`/`cx`, optimization level 1, seed 7.
At fixed default precision the circuit improvements reduce all-to-all CX
count by **27.7%** and Fez CZ count at level 1 by **24.0%**. With the routing
optimization, the Fez reduction is **35.0%**. The smallest 6-bit circuit is
**71.8%** below the original CZ count, but that comparison also changes phase
precision. All six routing trials and physical layouts are saved in
[feasibility.json](feasibility.json).

## Calibration and timing assessment

| Diagnostic | Selected 6-bit circuit | Selected 12-bit circuit |
| --- | ---: | ---: |
| Gate-duration critical path | 4.025 ms | 9.267 ms |
| Median active-qubit T1 | 126.9 µs | 124.2 µs |
| Median active-qubit T2 | 89.84 µs | 113.0 µs |
| Duration / median T2 | 44.8 | 82.0 |
| Usage-weighted average CZ error | 0.2344% | 0.2409% |
| Calibration-error cost | 177.47 | 418.97 |
| Instructions missing error data | 0 | 0 |

Timing is Qiskit's longest dependency path using the device's instruction
durations, excluding job overhead and shot repetition. It is a screening
estimate, not a measurement of the physical execution schedule.
[Qiskit duration API](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.QuantumCircuit#estimate_duration).

The cost sums `-log(1-error)` over all instructions with error data,
including readout. Treating the calibration errors as independent would
give a product of instruction fidelities with base-10 logarithm **−77.07**
for the smaller circuit. **That product is a ranking heuristic, not a
factoring success probability.** Reported average gate errors are not
literal probabilities of independent damaging events, some errors do not
change measured outcomes, and correlations and drift are unmodeled.
[IBM instruction properties](https://quantum.cloud.ibm.com/docs/en/api/qiskit/2.5/qiskit.transpiler.InstructionProperties).

Similarly, comparing total duration to median T2 is diagnostic: different
qubits carry information at different times, so it is not an exact model
of coherence decay. The report preserves all used instruction calibrations
and active-qubit T1/T2 values. **No full noisy simulation was performed.**
The large gate count, error accumulation, and timing disparity together
provide a sufficient practical reason to stop this bounded attempt.

The smallest candidate exceeds the previous demonstrations' conservative
200-gate / 200-depth screening budget by factors of about **301** and **209**.
The successful 15/21 circuits used only **49–79 CZ gates**. Those budgets are
experiment choices, not physical impossibility thresholds. This assessment
does not establish that all approaches to factoring 35 on hardware fail.

## Validation and reproducibility

The complete suite passes **318 tests**, including **173 arithmetic tests**.
Checks cover all valid multiplier inputs for both range-check modes,
control-off and unused states in the default mode, scratch cleanup,
complex superpositions and phases in Qiskit, every exponent at default
precision, reduced precision, and independent Aer sampling. The earlier
15/21 hardware circuit tests remain included.

```sh
python -m pytest -q
python -m shors_algorithm.arithmetic_experiment --number 35 --base 2 --method aer-mps --resources
python -m shors_algorithm.arithmetic_experiment --number 35 --base 2 --counting-qubits 6 --method aer-mps --resources
python -m shors_algorithm.feasibility --backend ibm_fez --output results/my_35_feasibility.json
```

Only the last command needs the saved IBM account. It reads calibration
data and compiles six candidates; it cannot submit a hardware job. Use a
new output filename. Future calibrations or compiler versions may change
the resource selection. The experiment CLI caps the modulus at 35.

Saved artifacts:

- [12-bit Aer counts and resources](N35_a2_t12_aer_mps.json).
- [6-bit Aer counts and resources](N35_a2_t6_aer_mps.json).
- [Exact sparse probabilities and Aer comparisons](simulator_comparison.json).
- [Compiler trials, versions, source hashes, and calibration diagnostics](feasibility.json).
- [Initial baseline](../arithmetic_2026-11-16/REPORT.md).
- [Successful 15/21 hardware experiment](../ibm_fez_2026-11-16/REPORT.md).
