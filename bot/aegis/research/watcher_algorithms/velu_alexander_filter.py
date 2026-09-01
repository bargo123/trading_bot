"""Velu, Hardy, and Nehren's Alexander percentage-filter rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "velu_alexander_filter"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_filter_current_price",
    "velu_filter_reference_extreme",
    "velu_filter_reference_type",
    "velu_filter_threshold",
    "velu_filter_position",
    "velu_filter_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_filter_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("velu_filter_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    current = number(first(state, "velu_filter_current_price"))
    extreme = number(first(state, "velu_filter_reference_extreme"))
    threshold = number(first(state, "velu_filter_threshold"))
    reference_type = str(first(state, "velu_filter_reference_type") or "").strip().lower().replace(" ", "_")
    position = str(first(state, "velu_filter_position") or "").strip().lower().replace(" ", "_")
    if (
        candidate_side is None
        or current is None
        or extreme is None
        or threshold is None
        or current <= 0.0
        or extreme <= 0.0
        or not 0.0 < threshold < 1.0
        or reference_type not in {"past_low", "past_high", "subsequent_low", "subsequent_high"}
        or position not in {"flat", "long", "short"}
    ):
        result["velu_filter_action"] = "INVALID_FILTER_INPUT"
        result["reasons"] = [
            "the percentage filter needs positive observed prices, a bounded threshold, and an explicit reference/position state"
        ]
        return result

    move_fraction = (current - extreme) / extreme
    result.update(
        {
            "velu_filter_current_price": current,
            "velu_filter_reference_extreme": extreme,
            "velu_filter_threshold": threshold,
            "velu_filter_reference_type": reference_type,
            "velu_filter_position": position,
            "velu_filter_move_fraction": move_fraction,
        }
    )

    signal = None
    action = "FILTER_NOT_REACHED"
    reason = "the observed percentage move has not reached the configured Alexander filter"
    if reference_type == "past_low" and position == "flat" and move_fraction >= threshold:
        signal = "BUY"
        action = "ENTER_LONG"
        reason = "price rose by at least the configured percentage from the observed past low"
    elif reference_type == "subsequent_high" and position == "long" and move_fraction <= -threshold:
        signal = "SELL"
        action = "REVERSE_TO_SHORT"
        reason = "price fell by at least the configured percentage from the observed subsequent high"
    elif reference_type == "subsequent_low" and position == "short" and move_fraction >= threshold:
        signal = "BUY"
        action = "REVERSE_TO_LONG"
        reason = "price rose by at least the configured percentage from the observed subsequent low"
    elif reference_type == "past_high" and position == "flat" and move_fraction <= -threshold:
        signal = "SELL"
        action = "ENTER_SHORT"
        reason = "price fell by at least the configured percentage from the observed past high"

    result["velu_filter_action"] = action
    return with_direction(result, state, signal, reason)
