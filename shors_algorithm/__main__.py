"""Run an ideal local order-finding experiment: python -m shors_algorithm."""

import argparse

from . import simulate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number", type=int, default=21, help="modulus to factor (default: 21)")
    parser.add_argument("--base", type=int, default=2, help="base coprime to the modulus (default: 2)")
    parser.add_argument("--counting-qubits", type=int)
    parser.add_argument("--shots", type=int, default=2048)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    # Both statevector memory and this circuit synthesis grow exponentially.
    # The library remains unrestricted for explicit circuit experiments.
    if args.number > 31 or (args.counting_qubits is not None and args.counting_qubits > 12):
        parser.error("this local demo is limited to N <= 31 and at most 12 counting qubits")
    try:
        result = simulate(
            args.base, args.number, counting_qubits=args.counting_qubits,
            shots=args.shots, seed=args.seed,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(f"N = {result.modulus}, a = {result.base}")
    print(f"Qubits: {result.counting_qubits} counting + {result.work_qubits} work")
    print(f"Shots: {sum(result.counts.values())} (ideal local simulation)")
    print(f"Verified periods: {result.periods}")
    if result.factors is None:
        print("No factors recovered. Try more shots or a different coprime base.")
        return 1
    print(f"Factors: {result.factors[0]} * {result.factors[1]} = {result.modulus}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
