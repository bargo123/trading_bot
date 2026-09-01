"""Aldridge futures-versus-spot basis-arbitrage perspective."""
from __future__ import annotations

from ._aldridge_arbitrage_common import dislocation

ALGORITHM_ID = "aldridge_futures_basis_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_basis_residual", "aldridge_basis_threshold", "aldridge_basis_net_edge_after_cost", "aldridge_basis_direction", "aldridge_basis_quotes_synchronized", "aldridge_basis_data_provenance")


def evaluate(state):
    return dislocation(state, algorithm_id=ALGORITHM_ID, keys=KEYS, residual_key="aldridge_basis_residual", threshold_key="aldridge_basis_threshold", edge_key="aldridge_basis_net_edge_after_cost", direction_key="aldridge_basis_direction", provenance_key="aldridge_basis_data_provenance", synchronization_key="aldridge_basis_quotes_synchronized", output_prefix="aldridge_basis", warning="basis trading requires synchronized spot/futures prices and carry-aware costs")
