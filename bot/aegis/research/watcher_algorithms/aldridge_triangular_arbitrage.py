"""Aldridge triangular FX-arbitrage perspective."""
from __future__ import annotations

from ._aldridge_arbitrage_common import dislocation

ALGORITHM_ID = "aldridge_triangular_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_triangle_residual", "aldridge_triangle_threshold", "aldridge_triangle_net_edge_after_cost", "aldridge_triangle_direction", "aldridge_triangle_quotes_synchronized", "aldridge_triangle_data_provenance")


def evaluate(state):
    return dislocation(state, algorithm_id=ALGORITHM_ID, keys=KEYS, residual_key="aldridge_triangle_residual", threshold_key="aldridge_triangle_threshold", edge_key="aldridge_triangle_net_edge_after_cost", direction_key="aldridge_triangle_direction", provenance_key="aldridge_triangle_data_provenance", synchronization_key="aldridge_triangle_quotes_synchronized", output_prefix="aldridge_triangle", warning="triangular arbitrage needs simultaneous executable quotes and all-leg costs")
