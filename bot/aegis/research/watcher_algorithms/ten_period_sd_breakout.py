"""High Probability Trading's ten-period breakout with a half-SD buffer."""
from __future__ import annotations

from ._common import absent, base, first, number, values, with_direction

ALGORITHM_ID = "ten_period_sd_breakout"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "breakout_lookback", "breakout_high_10", "breakout_low_10",
    "breakout_sd", "breakout_buffer_sd", "current_price",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("ten_period_range_and_current_price",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    lookback = number(first(state, "breakout_lookback"))
    high = number(first(state, "breakout_high_10"))
    low = number(first(state, "breakout_low_10"))
    sd = number(first(state, "breakout_sd"))
    current = number(first(state, "current_price", "mid"))
    buffer_sd = number(first(state, "breakout_buffer_sd"))
    buffer_sd = 0.5 if buffer_sd is None else buffer_sd
    if lookback != 10:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "WAIT"
        result["reasons"] = ["the source rule is defined for a ten-period breakout"]
        return result
    if None in {high, low, sd, current} or sd <= 0 or low >= high or buffer_sd < 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_ten_period_range_and_standard_deviation"]
        return result
    result["rule_parameters"] = {"lookback": 10, "buffer_sd": buffer_sd}
    upper_trigger = high + buffer_sd * sd
    lower_trigger = low - buffer_sd * sd
    if current >= upper_trigger and current <= lower_trigger:
        result["view"] = "WAIT"
        result["reasons"] = ["ten-period breakout geometry is internally inconsistent"]
        return result
    if current >= upper_trigger:
        return with_direction(result, state, "BUY", "price cleared the ten-period high plus the source SD buffer")
    if current <= lower_trigger:
        return with_direction(result, state, "SELL", "price cleared the ten-period low minus the source SD buffer")
    result["view"] = "WAIT"
    result["reasons"] = ["price has not cleared the ten-period breakout trigger"]
    return result
