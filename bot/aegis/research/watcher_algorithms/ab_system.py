"""Carver's documented A/B early profit/loss-taker system for research."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "ab_system"
SOURCES = ("Robert Carver — Systematic Trading",)
KEYS = (
    "ab_mode", "ab_a", "ab_b", "ab_entry_price", "ab_deviation",
    "ab_high_since_entry", "ab_low_since_entry", "current_price",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("a_and_b_position_rule",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    mode = strings(state, "ab_mode")
    a = number(first(state, "ab_a"))
    b = number(first(state, "ab_b"))
    entry = number(first(state, "ab_entry_price"))
    deviation = number(first(state, "ab_deviation"))
    current = number(first(state, "current_price", "mid"))
    if mode not in {"profit_taker", "loss_taker"} or None in {a, b, entry, deviation, current} or a <= 0 or b <= 0 or deviation <= 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_a_and_b_position_rule"]
        return result
    result["rule_parameters"] = {"mode": mode, "a": a, "b": b, "deviation": deviation}
    candidate_side = str(first(state, "side", "position_side") or "").strip().upper()
    if candidate_side == "BUY":
        high = number(first(state, "ab_high_since_entry"))
        if high is None:
            result["view"] = "MISSING_DATA"
            result["missing_inputs"] = ["ab_high_since_entry"]
            return result
        if current >= entry + a * deviation:
            return with_direction(result, state, "SELL", "A/B profit target was reached for a long position")
        if current <= high - b * deviation:
            return with_direction(result, state, "SELL", "A/B trailing stop was reached for a long position")
    elif candidate_side == "SELL":
        low = number(first(state, "ab_low_since_entry"))
        if low is None:
            result["view"] = "MISSING_DATA"
            result["missing_inputs"] = ["ab_low_since_entry"]
            return result
        if current <= entry - a * deviation:
            return with_direction(result, state, "BUY", "A/B profit target was reached for a short position")
        if current >= low + b * deviation:
            return with_direction(result, state, "BUY", "A/B trailing stop was reached for a short position")
    result["view"] = "WAIT"
    result["reasons"] = ["A/B profit and trailing-stop thresholds have not been reached"]
    return result
