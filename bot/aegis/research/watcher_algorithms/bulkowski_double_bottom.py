"""Bulkowski double-bottom confirmation and measured-move perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "bulkowski_double_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = (
    "bulkowski_double_variant",
    "bulkowski_prior_trend",
    "bulkowski_intervening_move_pct",
    "bulkowski_bottom_variation_pct",
    "bulkowski_bottom_separation_weeks",
    "bulkowski_confirmation_price",
    "bulkowski_breakout_close",
    "bulkowski_lowest_low",
    "bulkowski_stop_buffer",
    "bulkowski_data_provenance",
)
VARIANTS = {"adam_adam", "adam_eve", "eve_adam", "eve_eve"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "bulkowski_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("bulkowski_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    variant = normalized_status(first(state, "bulkowski_double_variant")).replace(" ", "_")
    if variant not in VARIANTS:
        result["reasons"] = ["the double-bottom family must be an observed Adam/Eve variant"]
        return result
    if normalized_status(first(state, "bulkowski_prior_trend")) != "down":
        result["reasons"] = ["a double bottom requires a downward price trend into the pattern"]
        return result
    move = number(first(state, "bulkowski_intervening_move_pct"))
    variation = number(first(state, "bulkowski_bottom_variation_pct"))
    separation = number(first(state, "bulkowski_bottom_separation_weeks"))
    confirmation = number(first(state, "bulkowski_confirmation_price"))
    breakout = number(first(state, "bulkowski_breakout_close"))
    lowest = number(first(state, "bulkowski_lowest_low"))
    buffer = number(first(state, "bulkowski_stop_buffer"))
    if any(value is None for value in (move, variation, separation, confirmation, breakout, lowest, buffer)):
        result["reasons"] = ["double-bottom structure, confirmation, and stop geometry must be finite observations"]
        return result
    if move < 10.0 or not 2.0 <= variation <= 5.0 or not 3.0 <= separation <= 8.0:
        result["reasons"] = ["the observed double bottom fails the source's intervening-rise, valley-variation, or separation guidelines"]
        return result
    if breakout <= confirmation:
        result["reasons"] = ["the double bottom has not closed above its confirmation line"]
        return result
    if buffer <= 0 or confirmation <= lowest:
        result["reasons"] = ["formation height and stop buffer must be positive"]
        return result
    result.update({
        "bulkowski_measure_target": confirmation + (confirmation - lowest),
        "bulkowski_stop_price": lowest - buffer,
        "bulkowski_confirmation_breakout": breakout,
        "bulkowski_double_variant": variant,
    })
    return with_direction(result, state, "BUY", "the observed double bottom closed above its confirmation line after the source structure tests")
