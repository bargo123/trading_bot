"""Bollinger-band location and reversion/expansion perspective."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "bollinger_bands"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Ernest Chan — Quantitative Trading",
    "Adam Grimes — The Art and Science of Technical Analysis",
)
KEYS = (
    "bollinger_middle", "bollinger_upper", "bollinger_lower", "bollinger_width",
    "bollinger_bandwidth", "bollinger_position", "bollinger_state", "bollinger_window_n",
    "breakout_state", "macd_state",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("bollinger_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    band_state = strings(state, "bollinger_state")
    breakout = strings(state, "breakout_state")
    if "below_lower" in band_state:
        return with_direction(result, state, "BUY", "price is below the observed lower band; reversion is a research hypothesis")
    if "above_upper" in band_state:
        return with_direction(result, state, "SELL", "price is above the observed upper band; reversion is a research hypothesis")
    if "breakout_up" in breakout and "upper" in band_state:
        return with_direction(result, state, "BUY", "upper-band expansion is accompanied by an observed upside break")
    if "breakout_down" in breakout and "lower" in band_state:
        return with_direction(result, state, "SELL", "lower-band expansion is accompanied by an observed downside break")
    result["view"] = "WAIT"
    result["reasons"] = ["price remains inside the observed Bollinger envelope without a decisive reversion or expansion state"]
    return result
