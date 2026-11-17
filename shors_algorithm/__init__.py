"""General reversible arithmetic and small-instance Shor demonstrations."""

from .arithmetic import (
    arithmetic_modular_multiplication,
    constant_adder,
    modular_adder,
    multiply_accumulate,
)
from .arithmetic_order_finding import (
    ArithmeticSimulationResult,
    arithmetic_order_finding_circuit,
    arithmetic_phase_probabilities,
    simulate_arithmetic,
)
from .modular import controlled_modular_multiplication, modular_multiplication
from .order_finding import (
    SimulationResult,
    factors_from_counts,
    factors_from_period,
    order_finding_circuit,
    recover_periods,
    simulate,
)

__all__ = [
    "ArithmeticSimulationResult",
    "SimulationResult",
    "arithmetic_modular_multiplication",
    "arithmetic_order_finding_circuit",
    "arithmetic_phase_probabilities",
    "constant_adder",
    "controlled_modular_multiplication",
    "factors_from_counts",
    "factors_from_period",
    "modular_multiplication",
    "modular_adder",
    "multiply_accumulate",
    "order_finding_circuit",
    "recover_periods",
    "simulate",
    "simulate_arithmetic",
]
