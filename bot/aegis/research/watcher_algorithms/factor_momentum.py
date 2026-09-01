"""Factor-score momentum selection with an as-of cross-sectional rank."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "factor_momentum"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum", "Richard Grinold and Ronald Kahn — Active Portfolio Management")
KEYS = ("factor_signal", "factor_score", "factor_rank_percentile", "factor_as_of")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("as_of_factor_momentum_rank",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = str(first(state, "factor_signal") or "").strip().upper()
    score = number(first(state, "factor_score"))
    rank = number(first(state, "factor_rank_percentile"))
    as_of = first(state, "factor_as_of")
    if signal not in {"BUY", "SELL"} or score is None or rank is None or not as_of:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["factor_score_rank_and_as_of"]
        return result
    if not 0 <= rank <= 1:
        result["view"] = "WAIT"
        result["reasons"] = ["factor rank is invalid"]
        return result
    if signal == "BUY" and rank >= 0.8 and score > 0:
        return with_direction(result, state, "BUY", "positive factor momentum is in the upper cross-sectional tail")
    if signal == "SELL" and rank <= 0.2 and score < 0:
        return with_direction(result, state, "SELL", "negative factor momentum is in the lower cross-sectional tail")
    result["view"] = "WAIT"
    result["reasons"] = ["factor momentum is not in a validated directional tail"]
    return result
