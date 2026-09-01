"""Cross-sectional momentum selection with explicit as-of universe ranking."""
from __future__ import annotations

from ._common import absent, base, direction, first, number, strings, values, with_direction

ALGORITHM_ID = "cross_sectional_momentum"
SOURCES = (
    "Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",
    "Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",
)
KEYS = ("momentum_rank_percentile", "rank_universe_n", "momentum_direction", "ranking_as_of")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("as_of_cross_sectional_rank",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    rank = number(first(state, "momentum_rank_percentile"))
    universe_n = number(first(state, "rank_universe_n"))
    signal = direction(first(state, "momentum_direction"))
    if rank is None or universe_n is None or signal not in {"BUY", "SELL"}:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["rank_universe_and_direction"]
        return result
    if not 0.0 <= rank <= 1.0 or universe_n < 10:
        result["view"] = "WAIT"
        result["reasons"] = ["cross-sectional rank is outside a valid universe or sample size"]
        return result
    result["selection_rule"] = "top_or_bottom_decile"
    if signal == "BUY" and rank >= 0.9:
        return with_direction(result, state, "BUY", "instrument is in the top decile of the point-in-time momentum universe")
    if signal == "SELL" and rank <= 0.1:
        return with_direction(result, state, "SELL", "instrument is in the bottom decile of the point-in-time momentum universe")
    result["view"] = "WAIT"
    result["reasons"] = ["cross-sectional momentum rank is not in the selected tail"]
    return result
