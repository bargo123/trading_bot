"""Read-only range-edge rejection/fade perspective."""
from __future__ import annotations

from ._common import base, first, normalized_status, values, with_direction

ALGORITHM_ID = "range_edge_fade"
SOURCES = (
    "Al Brooks — Trading Price Action Trading Ranges",
    "Ernest Chan — Quantitative Trading",
    "James Dalton — Markets in Profile",
)
KEYS = ("range_state", "regime", "balance_state", "range_position", "range_edge_rejection", "rejection")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("range_context", "edge_rejection"))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    regime = normalized_status(first(state, "range_state", "regime", "balance_state"))
    if not regime:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["range_context"]
        result["reasons"] = ["an edge rejection is not interpretable without an explicit range regime"]
        return result
    if regime in {"trend", "trending", "initiative", "initiative up", "initiative down"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["range-edge fade is not applicable in an initiative trend state"]
        return result
    if regime not in {"range", "range bound", "balanced", "balance"}:
        result["view"] = "WAIT"
        result["reasons"] = ["range regime is not explicitly classified"]
        return result
    rejection = normalized_status(first(state, "range_edge_rejection", "rejection"))
    if not rejection:
        result["view"] = "WAIT"
        result["reasons"] = ["range regime is present but no edge rejection/reclaim is observed"]
        return result
    if any(token in rejection for token in ("lower", "support hold", "bullish", "reclaimed")) and "upper" not in rejection:
        return with_direction(result, state, "BUY", "lower range edge was rejected or reclaimed")
    if any(token in rejection for token in ("upper", "resistance", "bearish")) and "lower" not in rejection:
        return with_direction(result, state, "SELL", "upper range edge was rejected")
    result["view"] = "WAIT"
    result["reasons"] = ["edge observation is ambiguous"]
    return result
