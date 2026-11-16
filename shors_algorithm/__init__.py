"""Generated modular multiplication and small-instance Shor order finding."""

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
    "SimulationResult",
    "controlled_modular_multiplication",
    "factors_from_counts",
    "factors_from_period",
    "modular_multiplication",
    "order_finding_circuit",
    "recover_periods",
    "simulate",
]
