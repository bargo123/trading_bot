"""Aldridge index-versus-composition arbitrage perspective."""
from __future__ import annotations

from ._aldridge_arbitrage_common import dislocation

ALGORITHM_ID = "aldridge_index_composition_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_index_residual", "aldridge_index_threshold", "aldridge_index_net_edge_after_cost", "aldridge_index_direction", "aldridge_index_quotes_synchronized", "aldridge_index_data_provenance")


def evaluate(state):
    return dislocation(state, algorithm_id=ALGORITHM_ID, keys=KEYS, residual_key="aldridge_index_residual", threshold_key="aldridge_index_threshold", edge_key="aldridge_index_net_edge_after_cost", direction_key="aldridge_index_direction", provenance_key="aldridge_index_data_provenance", synchronization_key="aldridge_index_quotes_synchronized", output_prefix="aldridge_index", warning="index composition arbitrage requires synchronized index and component prices")
