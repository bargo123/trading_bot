"""John Carter's third-brick reversal confirmation study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_brick_reversal"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_brick_directions",
    "carter_brick_reference_high",
    "carter_brick_reference_low",
    "carter_brick_break_price",
    "carter_brick_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_brick_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_brick_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    directions = first(state, "carter_brick_directions")
    if not isinstance(directions, (list, tuple)) or len(directions) < 4:
        result["view"] = "WAIT"
        result["reasons"] = ["the brick study needs a causal sequence containing the reversal and three bricks"]
        return result
    normalized = [normalized_status(value).upper() for value in directions]
    if any(value not in {"UP", "DOWN"} for value in normalized):
        result["view"] = "WAIT"
        result["reasons"] = ["brick directions must be explicit UP or DOWN observations"]
        return result
    latest = normalized[-1]
    if normalized[-3:] != [latest, latest, latest] or normalized[-4] == latest:
        result["view"] = "WAIT"
        result["reasons"] = ["the latest brick run does not represent a newly shifted three-brick formation"]
        return result
    reference_high = number(first(state, "carter_brick_reference_high"))
    reference_low = number(first(state, "carter_brick_reference_low"))
    break_price = number(first(state, "carter_brick_break_price"))
    if any(value is None for value in (reference_high, reference_low, break_price)):
        result["view"] = "WAIT"
        result["reasons"] = ["the third-brick reference and break price must be finite observations"]
        return result
    if latest == "UP":
        if break_price <= reference_high:
            result["view"] = "WAIT"
            result["reasons"] = ["the upward reversal has not broken the third-brick reference high"]
            return result
        signal = "BUY"
        reference = reference_high
    else:
        if break_price >= reference_low:
            result["view"] = "WAIT"
            result["reasons"] = ["the downward reversal has not broken the third-brick reference low"]
            return result
        signal = "SELL"
        reference = reference_low
    result["carter_brick_reference_price"] = reference
    result["carter_brick_signal"] = signal
    return with_direction(result, state, signal, "three shifted bricks broke the source third-brick reference")
