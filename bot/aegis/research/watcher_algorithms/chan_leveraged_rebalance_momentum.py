"""Chan's near-close leveraged-fund rebalancing momentum study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction

ALGORITHM_ID = "chan_leveraged_rebalance_momentum"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_rebalance_underlying_return",
    "chan_rebalance_threshold",
    "chan_rebalance_minutes_to_close",
    "chan_rebalance_window_minutes",
    "chan_rebalance_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "chan_rebalance_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("chan_rebalance_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    underlying = number(first(state, "chan_rebalance_underlying_return"))
    threshold = number(first(state, "chan_rebalance_threshold"))
    minutes = number(first(state, "chan_rebalance_minutes_to_close"))
    window = number(first(state, "chan_rebalance_window_minutes"))
    if underlying is None or threshold is None or minutes is None or window is None or threshold <= 0 or minutes < 0 or window <= 0:
        result["chan_rebalance_assessment"] = "INVALID_REBALANCE_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["underlying return, threshold, and close-window observations must be valid"]
        return result
    if minutes > window:
        result["chan_rebalance_assessment"] = "OUTSIDE_CLOSE_WINDOW"
        result["view"] = "WAIT"
        result["reasons"] = ["the leveraged-rebalance momentum study is restricted to the measured near-close window"]
        return result
    if abs(underlying) < threshold or underlying == 0:
        result["chan_rebalance_assessment"] = "INSUFFICIENT_UNDERLYING_MOVE"
        result["view"] = "WAIT"
        result["reasons"] = ["the underlying move did not reach the measured rebalancing threshold"]
        return result
    result["chan_rebalance_assessment"] = "CLOSE_REBALANCE_MOMENTUM"
    return with_direction(result, state, "BUY" if underlying > 0 else "SELL", "the large near-close underlying move supplies the rebalancing direction")
