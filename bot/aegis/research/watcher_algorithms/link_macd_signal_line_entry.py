"""Marcel Link's MACD-line versus signal-line directional perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "link_macd_signal_line_entry"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_macd_line",
    "link_macd_signal_line",
    "link_macd_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_macd_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_macd_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    line = number(first(state, "link_macd_line"))
    signal_line = number(first(state, "link_macd_signal_line"))
    if line is None or signal_line is None:
        result["link_macd_action"] = "INVALID_MACD_INPUT"
        result["reasons"] = ["MACD and signal-line values must be finite observations"]
        return result
    result.update(
        {
            "link_macd_line_minus_signal": line - signal_line,
            "directional_claim": True,
        }
    )
    if candidate_side == "BUY" and line > signal_line:
        return with_direction(
            {**result, "link_macd_action": "BUY_MACD_ABOVE_SIGNAL"},
            state,
            "BUY",
            "the observed MACD line is above its signal line",
        )
    if candidate_side == "SELL" and line < signal_line:
        return with_direction(
            {**result, "link_macd_action": "SELL_MACD_BELOW_SIGNAL"},
            state,
            "SELL",
            "the observed MACD line is below its signal line",
        )
    result["link_macd_action"] = "NO_MACD_RELATIONSHIP"
    result["reasons"] = ["the MACD line does not support the copied candidate side"]
    return result
