"""Marcel Link's stochastic %K/%D cross entry perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "link_stochastic_cross_entry"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_stoch_fast",
    "link_stoch_slow",
    "link_stoch_fast_previous",
    "link_stoch_slow_previous",
    "link_stoch_oversold",
    "link_stoch_overbought",
    "link_stoch_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_stoch_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_stoch_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    fast = number(first(state, "link_stoch_fast"))
    slow = number(first(state, "link_stoch_slow"))
    fast_previous = number(first(state, "link_stoch_fast_previous"))
    slow_previous = number(first(state, "link_stoch_slow_previous"))
    oversold = number(first(state, "link_stoch_oversold"))
    overbought = number(first(state, "link_stoch_overbought"))
    if (
        any(value is None for value in (fast, slow, fast_previous, slow_previous, oversold, overbought))
        or any(not 0.0 <= value <= 100.0 for value in (fast, slow, fast_previous, slow_previous, oversold, overbought))
        or not oversold < overbought
    ):
        result["link_stoch_action"] = "INVALID_STOCHASTIC_INPUT"
        result["reasons"] = ["stochastic lines and thresholds must be bounded observations with oversold below overbought"]
        return result

    cross_up = fast_previous <= slow_previous and fast > slow
    cross_down = fast_previous >= slow_previous and fast < slow
    buy_zone = fast > oversold and slow > oversold
    sell_zone = fast < overbought and slow < overbought
    slow_bottomed = first(state, "link_stoch_slow_bottomed") is True
    result.update(
        {
            "link_stoch_cross": "UP" if cross_up else "DOWN" if cross_down else "NONE",
            "link_stoch_slow_bottomed": slow_bottomed,
            "link_stoch_cross_zone": "ABOVE_OVERSOLD" if buy_zone else "BELOW_OVERBOUGHT" if sell_zone else "OUTSIDE_SOURCE_ZONE",
            "directional_claim": True,
        }
    )
    if candidate_side == "BUY" and cross_up and buy_zone:
        result["link_stoch_action"] = "BUY_STOCHASTIC_CROSS"
        result["link_stoch_cross_strength"] = "STRONGER_AFTER_SLOW_BOTTOM" if slow_bottomed else "CROSS_WITHOUT_SLOW_BOTTOM_CONFIRMATION"
        return with_direction(result, state, "BUY", "fast stochastic line crossed above slow line after the source oversold zone")
    if candidate_side == "SELL" and cross_down and sell_zone:
        result["link_stoch_action"] = "SELL_STOCHASTIC_CROSS"
        result["link_stoch_cross_strength"] = "STRONGER_AFTER_SLOW_BOTTOM" if slow_bottomed else "CROSS_WITHOUT_SLOW_BOTTOM_CONFIRMATION"
        return with_direction(result, state, "SELL", "fast stochastic line crossed below slow line before the source overbought zone")
    result["link_stoch_action"] = "NO_STOCHASTIC_CROSS"
    result["reasons"] = ["the stochastic cross is absent or is not in the source directional threshold zone"]
    return result
