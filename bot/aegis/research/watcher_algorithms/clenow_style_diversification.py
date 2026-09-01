"""Clenow's monthly diversification across trend, counter-trend, and curve styles."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, normalized_status, values

ALGORITHM_ID = "clenow_style_diversification"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = ("clenow_style_weights", "clenow_style_rebalance_frequency", "clenow_style_data_provenance")
_STYLES = ("trend_following", "counter_trend", "curve_trading")


def evaluate(state):
    found = values(state, *KEYS)
    weights = first(state, "clenow_style_weights")
    missing = []
    if not isinstance(weights, dict):
        missing.append("clenow_style_weights")
    if first(state, "clenow_style_rebalance_frequency") is None:
        missing.append("clenow_style_rebalance_frequency")
    if not explicitly_observed(first(state, "clenow_style_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("clenow_style_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    if set(weights) != set(_STYLES):
        result["clenow_style_assessment"] = "INVALID_STYLE_SET"
        result["view"] = "WAIT"
        result["reasons"] = ["the source blend contains trend-following, counter-trend, and curve-trading styles"]
        return result
    numeric = {key: float(value) if isinstance(value, (int, float)) else math.nan for key, value in weights.items()}
    if any(not math.isfinite(value) or value < 0 for value in numeric.values()) or abs(sum(numeric.values()) - 1.0) > 1e-9:
        result["clenow_style_assessment"] = "INVALID_STYLE_WEIGHTS"
        result["view"] = "WAIT"
        result["reasons"] = ["style weights must be finite non-negative values summing to one"]
        return result
    if normalized_status(first(state, "clenow_style_rebalance_frequency")) != "monthly":
        result["clenow_style_assessment"] = "REBALANCE_FREQUENCY_MISMATCH"
        result["view"] = "WAIT"
        result["reasons"] = ["the source demonstration rebalances the three-style blend monthly"]
        return result
    result["clenow_style_assessment"] = "VALID_EQUAL_STYLE_BLEND"
    result["clenow_style_action"] = "REBALANCE_MONTHLY"
    result["clenow_style_weights"] = numeric
    result["reasons"] = ["the observed style blend diversifies trend, counter-trend, and curve approaches"]
    return result
