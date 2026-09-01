"""Van Tharp failed-test reversal setup."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "tharp_failed_test_reversal"
SOURCES = ("Van K. Tharp — Trade Your Way to Financial Freedom",)
KEYS = (
    "tharp_test_extreme_direction",
    "tharp_test_returned_inside",
    "tharp_test_reversal_direction",
    "tharp_test_confirmation",
    "tharp_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present"}


def _direction(value) -> str | None:
    value = normalized_status(value)
    if value in {"up", "buy", "long", "bull", "bullish"}:
        return "BUY"
    if value in {"down", "sell", "short", "bear", "bearish"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("failed_test_sequence",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not explicitly_observed(first(state, "tharp_data_provenance"), accepted=("observed", "measured", "timestamped", "journal")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["tharp_data_provenance"]
        result["reasons"] = ["failed-test classification requires an observed timestamped sequence"]
        return result
    extreme = normalized_status(first(state, "tharp_test_extreme_direction"))
    expected = "SELL" if extreme in {"up", "high", "top"} else "BUY" if extreme in {"down", "low", "bottom"} else None
    if expected is None or not _truth(first(state, "tharp_test_returned_inside")):
        result["view"] = "WAIT"
        result["tharp_failed_test_assessment"] = "NO_FAILED_TEST"
        result["reasons"] = ["the extreme was not followed by an observed return inside the tested boundary"]
        return result
    if not explicitly_confirmed(first(state, "tharp_test_confirmation")) and not _truth(first(state, "tharp_test_confirmation")):
        result["view"] = "WAIT"
        result["tharp_failed_test_assessment"] = "TIMING_NOT_CONFIRMED"
        result["reasons"] = ["a failed test still needs a separate reversal confirmation"]
        return result
    reversal = _direction(first(state, "tharp_test_reversal_direction"))
    if reversal != expected:
        result["view"] = "WAIT"
        result["tharp_failed_test_assessment"] = "REVERSAL_DIRECTION_CONFLICT"
        result["reasons"] = ["the recorded reversal direction is not opposite the tested extreme"]
        return result
    result["tharp_failed_test_assessment"] = "CONFIRMED_REVERSAL"
    return with_direction(result, state, expected, "an extreme test failed, price returned inside, and reversal was confirmed")
