"""Marcel Link's RSI exit-from-extreme perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "link_rsi_extreme_exit"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_rsi_current",
    "link_rsi_previous",
    "link_rsi_oversold",
    "link_rsi_overbought",
    "link_rsi_extreme_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_rsi_extreme_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_rsi_extreme_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    current = number(first(state, "link_rsi_current"))
    previous = number(first(state, "link_rsi_previous"))
    oversold = number(first(state, "link_rsi_oversold"))
    overbought = number(first(state, "link_rsi_overbought"))
    if (
        any(value is None for value in (current, previous, oversold, overbought))
        or not all(0.0 <= value <= 100.0 for value in (current, previous, oversold, overbought))
        or not oversold < overbought
    ):
        result["link_rsi_extreme_action"] = "INVALID_RSI_EXTREME_INPUT"
        result["reasons"] = ["RSI values and extreme thresholds must be bounded observations with oversold below overbought"]
        return result

    exited_oversold = previous <= oversold < current
    exited_overbought = previous >= overbought > current
    result.update(
        {
            "link_rsi_exited_oversold": exited_oversold,
            "link_rsi_exited_overbought": exited_overbought,
            "directional_claim": True,
        }
    )
    if candidate_side == "BUY" and exited_oversold:
        return with_direction(
            {**result, "link_rsi_extreme_action": "BUY_OUT_OF_OVERSOLD"},
            state,
            "BUY",
            "RSI crossed out of the observed oversold zone",
        )
    if candidate_side == "SELL" and exited_overbought:
        return with_direction(
            {**result, "link_rsi_extreme_action": "SELL_OUT_OF_OVERBOUGHT"},
            state,
            "SELL",
            "RSI crossed out of the observed overbought zone",
        )
    result["link_rsi_extreme_action"] = "NO_RSI_EXTREME_EXIT"
    result["reasons"] = ["RSI did not cross out of the source extreme zone for the copied side"]
    return result
