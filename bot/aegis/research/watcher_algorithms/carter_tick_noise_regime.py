"""Carter's explicit breadth-$TICK noise and extreme bands."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "carter_tick_noise_regime"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = ("side", "carter_tick_value", "carter_tick_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "carter_tick_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("carter_tick_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    tick = number(first(state, "carter_tick_value"))
    result["directional_claim"] = False
    if tick is None:
        result["carter_tick_regime"] = "INVALID_TICK_INPUT"
        result["reasons"] = ["the breadth tick must be a finite observed number"]
        return result
    if abs(tick) <= 400.0:
        regime = "NOISE"
        reason = "the source treats readings between minus and plus 400 as non-conviction noise"
    elif tick >= 1000.0:
        regime = "EXTREME_BUYING_PRESSURE"
        reason = "the observed tick reached the source plus-1000 extreme band"
    elif tick <= -1000.0:
        regime = "EXTREME_SELLING_PRESSURE"
        reason = "the observed tick reached the source minus-1000 extreme band"
    else:
        regime = "NON_CONVICTION_EXTREME_PROBE"
        reason = "the tick left the noise band but has not reached the source action extreme"
    result["carter_tick_regime"] = regime
    result["carter_tick_value"] = tick
    result["reasons"] = [reason]
    return result
