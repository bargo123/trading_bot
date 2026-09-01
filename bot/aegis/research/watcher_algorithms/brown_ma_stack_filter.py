"""Brown's moving-average stack filter for trend-direction selection."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, values, with_direction

ALGORITHM_ID = "brown_ma_stack_filter"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_ma_stack",
    "brown_trend_direction",
    "brown_ma_spread",
    "brown_ma_data_provenance",
)


def _direction(value):
    direction = normalized_status(value).upper()
    return direction if direction in {"BUY", "SELL"} else None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_ma_stack_and_trend",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    stack = normalized_status(first(state, "brown_ma_stack"))
    trend = _direction(first(state, "brown_trend_direction"))
    provenance = first(state, "brown_ma_data_provenance")
    if not stack or trend is None:
        result["brown_ma_assessment"] = "TREND_UNCLEAR"
        result["reasons"] = ["a clear stacked moving-average trend and direction were not observed"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "chart")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["brown_ma_data_provenance"]
        return result

    result["brown_trend_direction"] = trend
    if not any(token in stack for token in ("stacked", "spreading", "aligned")):
        result["brown_ma_assessment"] = "TREND_UNCLEAR"
        result["reasons"] = ["moving averages are flat, tight, mixed, or otherwise not clearly stacked"]
        return result

    result["brown_ma_assessment"] = "STACKED_TREND_CONFIRMED"
    return with_direction(result, state, trend, "a clearly stacked and spreading moving-average structure favors its direction")
