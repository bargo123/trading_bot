"""Pole's popcorn-process spread reversion rule.

Pole's Rule 4 treats a materially displaced spread as a local reversion
opportunity and unwinds it at the local mean.  The evaluator accepts only
point-in-time observed spread statistics; it is a Watcher perspective and
cannot place or manage a broker order.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction


ALGORITHM_ID = "pole_popcorn_reversion"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "side",
    "pole_spread_value",
    "pole_local_mean",
    "pole_local_scale",
    "pole_entry_multiple",
    "pole_exit_tolerance",
    "pole_popcorn_position",
    "pole_popcorn_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_popcorn_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("pole_popcorn_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in values(state, *KEYS)])
    spread = number(first(state, "pole_spread_value"))
    local_mean = number(first(state, "pole_local_mean"))
    local_scale = number(first(state, "pole_local_scale"))
    entry_multiple = number(first(state, "pole_entry_multiple"))
    exit_tolerance = number(first(state, "pole_exit_tolerance"))
    position = normalized_status(first(state, "pole_popcorn_position")).replace(" ", "_")
    if (
        any(value is None for value in (spread, local_mean, local_scale, entry_multiple, exit_tolerance))
        or local_scale <= 0.0
        or entry_multiple <= 0.0
        or exit_tolerance < 0.0
    ):
        result["pole_popcorn_action"] = "INVALID_SPREAD_INPUT"
        result["reasons"] = ["popcorn reversion needs finite mean/scale inputs with positive entry scale"]
        return result

    if position not in {"flat", "long_spread", "short_spread"}:
        result["pole_popcorn_action"] = "INVALID_POSITION"
        result["reasons"] = ["popcorn position must be flat, long_spread, or short_spread"]
        return result

    zscore = (spread - local_mean) / local_scale
    result.update(
        {
            "pole_popcorn_zscore": zscore,
            "pole_popcorn_entry_multiple": entry_multiple,
            "pole_popcorn_exit_tolerance": exit_tolerance,
            "pole_popcorn_exit_rule": "UNWIND_AT_LOCAL_MEAN",
            "pole_popcorn_position": position,
        }
    )

    if position == "long_spread":
        if abs(zscore) <= exit_tolerance:
            result["pole_popcorn_action"] = "UNWIND_LONG_SPREAD_AT_MEAN"
            result["pole_popcorn_exit_triggered"] = True
            result["reasons"] = ["long spread has returned to the observed local mean band"]
        else:
            result["pole_popcorn_action"] = "HOLD_LONG_SPREAD"
            result["pole_popcorn_exit_triggered"] = False
            result["reasons"] = ["long spread has not returned to the observed local mean band"]
        return result

    if position == "short_spread":
        if abs(zscore) <= exit_tolerance:
            result["pole_popcorn_action"] = "UNWIND_SHORT_SPREAD_AT_MEAN"
            result["pole_popcorn_exit_triggered"] = True
            result["reasons"] = ["short spread has returned to the observed local mean band"]
        else:
            result["pole_popcorn_action"] = "HOLD_SHORT_SPREAD"
            result["pole_popcorn_exit_triggered"] = False
            result["reasons"] = ["short spread has not returned to the observed local mean band"]
        return result

    result["pole_popcorn_exit_triggered"] = False
    if zscore >= entry_multiple:
        result["pole_popcorn_action"] = "ENTER_SHORT_SPREAD"
        return with_direction(
            result,
            state,
            "SELL",
            "observed spread is sufficiently above its local mean for a popcorn-process reversion study",
        )
    if zscore <= -entry_multiple:
        result["pole_popcorn_action"] = "ENTER_LONG_SPREAD"
        return with_direction(
            result,
            state,
            "BUY",
            "observed spread is sufficiently below its local mean for a popcorn-process reversion study",
        )

    result["pole_popcorn_action"] = "WAIT_IN_LOCAL_BAND"
    result["reasons"] = ["spread displacement has not reached the observed entry multiple"]
    return result

