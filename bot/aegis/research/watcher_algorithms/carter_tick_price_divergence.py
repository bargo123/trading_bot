"""Carter's price-versus-$TICK divergence perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction

ALGORITHM_ID = "carter_tick_price_divergence"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "side",
    "carter_tick_price_change",
    "carter_tick_change",
    "carter_tick_divergence_min_abs",
    "carter_tick_divergence_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "carter_tick_divergence_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("carter_tick_divergence_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    price_change = number(first(state, "carter_tick_price_change"))
    tick_change = number(first(state, "carter_tick_change"))
    minimum = number(first(state, "carter_tick_divergence_min_abs"))
    result["directional_claim"] = True
    if price_change is None or tick_change is None or minimum is None or minimum <= 0:
        result["carter_tick_divergence_action"] = "INVALID_DIVERGENCE_INPUT"
        result["reasons"] = ["price change, tick change, and minimum divergence must be finite observations"]
        return result
    if price_change == 0.0 or abs(tick_change) < minimum:
        result["carter_tick_divergence_action"] = "DIVERGENCE_TOO_SMALL"
        result["reasons"] = ["the observed price change must be nonzero and the tick change must reach its supplied threshold"]
        return result
    result.update({"carter_tick_price_change": price_change, "carter_tick_change": tick_change})
    if price_change < 0 < tick_change:
        result["carter_tick_divergence_action"] = "BULLISH_DIVERGENCE"
        return with_direction(result, state, "BUY", "price made a lower low while the observed tick made a higher low")
    if price_change > 0 > tick_change:
        result["carter_tick_divergence_action"] = "BEARISH_DIVERGENCE"
        return with_direction(result, state, "SELL", "price made a higher high while the observed tick made a lower high")
    result["carter_tick_divergence_action"] = "NO_DIVERGENCE"
    result["reasons"] = ["price and tick moved in the same direction or one did not establish a new extreme"]
    return result
