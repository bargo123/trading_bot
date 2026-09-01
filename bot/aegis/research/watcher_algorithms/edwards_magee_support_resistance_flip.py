"""Edwards-Magee support/resistance role reversal proxy."""
from __future__ import annotations

from ._common import base, em_missing, first, number, normalized_status, explicitly_confirmed, with_direction

ALGORITHM_ID = "edwards_magee_support_resistance_flip"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = ("em_sr_role", "em_sr_retest", "em_sr_confirmation", "em_sr_break_margin_pips")


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    role = normalized_status(first(state, "em_sr_role"))
    if role not in {"resistance to support", "support to resistance"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["no post-break support/resistance role reversal is observed"]
        return result
    margin = number(first(state, "em_sr_break_margin_pips"))
    if normalized_status(first(state, "em_sr_retest")) != "held" or margin is None or margin < 1.0 or not explicitly_confirmed(first(state, "em_sr_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["the decisive break and successful retest are not both confirmed"]
        return result
    return with_direction(result, state, "BUY" if role == "resistance to support" else "SELL", "broken level held its new role on retest")
