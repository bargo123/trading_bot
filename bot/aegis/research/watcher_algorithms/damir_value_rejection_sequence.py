"""Laurentiu Damir's value-area rejection, response, and re-initiation study."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, number, values, with_direction

ALGORITHM_ID = "damir_value_rejection_sequence"
SOURCES = ("Laurentiu Damir — Price Action Breakdown",)
KEYS = (
    "damir_value_high",
    "damir_value_low",
    "damir_rejection_level",
    "damir_rejection_side",
    "damir_tail_or_excess_observed",
    "damir_first_initiative_direction",
    "damir_responsive_move_to_value",
    "damir_second_initiative_direction",
    "damir_second_initiative_confirmed",
    "damir_value_rejection_provenance",
    "damir_rejection_stop_pips",
    "damir_rejection_target_pips",
)


def _truth(value: object) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "present", "valid"}


def _direction(value: object) -> str | None:
    normalized = normalized_status(value)
    if normalized in {"up", "uptrend", "bull", "bullish", "buy", "long"}:
        return "up"
    if normalized in {"down", "downtrend", "bear", "bearish", "sell", "short"}:
        return "down"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "damir_value_rejection_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("damir_value_rejection_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    high = number(first(state, "damir_value_high"))
    low = number(first(state, "damir_value_low"))
    level = number(first(state, "damir_rejection_level"))
    rejection_side = normalized_status(first(state, "damir_rejection_side"))
    first_direction = _direction(first(state, "damir_first_initiative_direction"))
    second_direction = _direction(first(state, "damir_second_initiative_direction"))
    stop = number(first(state, "damir_rejection_stop_pips"))
    target = number(first(state, "damir_rejection_target_pips"))

    if any(value is None for value in (high, low, level)) or not low < high:
        result["reasons"] = ["value-area boundaries and rejection level must be finite and ordered"]
        return result
    if rejection_side not in {"above", "below"}:
        result["reasons"] = ["the rejected side of value must be observed as above or below"]
        return result
    if rejection_side == "below" and level > low:
        result["reasons"] = ["a below-value rejection must occur at or below value low"]
        return result
    if rejection_side == "above" and level < high:
        result["reasons"] = ["an above-value rejection must occur at or above value high"]
        return result
    if not _truth(first(state, "damir_tail_or_excess_observed")):
        result["reasons"] = ["a tail or excess rejection is required at the value boundary"]
        return result
    expected = "up" if rejection_side == "below" else "down"
    if first_direction != expected:
        result["reasons"] = ["the first initiative move does not leave the rejected value side"]
        return result
    if not _truth(first(state, "damir_responsive_move_to_value")):
        result["reasons"] = ["the first initiative move has not been followed by a responsive return to value"]
        return result
    if second_direction != expected or not _truth(first(state, "damir_second_initiative_confirmed")):
        result["reasons"] = ["the second initiative move has not confirmed continuation away from the rejected level"]
        return result
    if stop is None or target is None or stop <= 0 or target <= stop:
        result["reasons"] = ["the rejection setup requires positive source geometry with reward greater than risk"]
        return result

    signal = "BUY" if expected == "up" else "SELL"
    result.update(
        {
            "damir_rejection_sequence_confirmed": True,
            "damir_rejection_side": rejection_side,
            "damir_geometry": {"stop_pips": stop, "target_pips": target, "reward_risk": target / stop},
        }
    )
    return with_direction(result, state, signal, "tail/excess rejection, responsive return, and second initiative move agree")
