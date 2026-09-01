"""Point-and-figure breakout perspective with explicit box geometry."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, number, strings, values, with_direction

ALGORITHM_ID = "point_and_figure"
SOURCES = ("John J. Murphy — Technical Analysis of the Financial Markets", "Thomas Bulkowski — Encyclopedia of Chart Patterns")
KEYS = ("pnf_pattern", "pnf_direction", "pnf_confirmation", "pnf_box_size", "pnf_reversal_boxes")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_pnf_breakout_geometry",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = strings(state, "pnf_pattern")
    signal = strings(state, "pnf_direction")
    box = number(first(state, "pnf_box_size"))
    reversal = number(first(state, "pnf_reversal_boxes"))
    if box is None or reversal is None or box <= 0 or reversal < 1 or not explicitly_confirmed(first(state, "pnf_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["point-and-figure signal needs confirmed pattern and valid box/reversal geometry"]
        return result
    if "breakout" not in pattern:
        result["view"] = "WAIT"
        result["reasons"] = ["recorded point-and-figure pattern is not a breakout"]
        return result
    if "up" in signal or "top" in pattern:
        return with_direction(result, state, "BUY", "confirmed point-and-figure upside breakout")
    if "down" in signal or "bottom" in pattern:
        return with_direction(result, state, "SELL", "confirmed point-and-figure downside breakout")
    result["view"] = "WAIT"
    result["reasons"] = ["point-and-figure breakout direction is unresolved"]
    return result
