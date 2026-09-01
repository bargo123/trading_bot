"""Aldridge futures-versus-ETF lead-lag arbitrage perspective."""
from __future__ import annotations

from ._aldridge_arbitrage_common import dislocation

ALGORITHM_ID = "aldridge_futures_etf_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_futures_etf_residual", "aldridge_futures_etf_threshold", "aldridge_futures_etf_net_edge_after_cost", "aldridge_futures_etf_direction", "aldridge_futures_etf_quotes_synchronized", "aldridge_futures_etf_data_provenance")


def evaluate(state):
    return dislocation(state, algorithm_id=ALGORITHM_ID, keys=KEYS, residual_key="aldridge_futures_etf_residual", threshold_key="aldridge_futures_etf_threshold", edge_key="aldridge_futures_etf_net_edge_after_cost", direction_key="aldridge_futures_etf_direction", provenance_key="aldridge_futures_etf_data_provenance", synchronization_key="aldridge_futures_etf_quotes_synchronized", output_prefix="aldridge_futures_etf", warning="futures/ETF arbitrage requires synchronized executable legs and measured lead-lag costs")
