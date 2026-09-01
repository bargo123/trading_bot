"""Aldridge option-volatility-curve arbitrage perspective."""
from __future__ import annotations

from ._aldridge_arbitrage_common import dislocation

ALGORITHM_ID = "aldridge_volatility_curve_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_volatility_curve_residual", "aldridge_volatility_curve_threshold", "aldridge_volatility_curve_net_edge_after_cost", "aldridge_volatility_curve_direction", "aldridge_volatility_curve_stationarity", "aldridge_volatility_curve_data_provenance")


def evaluate(state):
    return dislocation(state, algorithm_id=ALGORITHM_ID, keys=KEYS, residual_key="aldridge_volatility_curve_residual", threshold_key="aldridge_volatility_curve_threshold", edge_key="aldridge_volatility_curve_net_edge_after_cost", direction_key="aldridge_volatility_curve_direction", provenance_key="aldridge_volatility_curve_data_provenance", validation_key="aldridge_volatility_curve_stationarity", output_prefix="aldridge_volatility_curve", warning="volatility-curve arbitrage requires a validated curve relationship and executable costs")
