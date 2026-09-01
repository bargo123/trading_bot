"""Edwards--Magee defensive exit versus reversal distinction."""
from __future__ import annotations

from ._common import absent, base, em_missing, explicitly_confirmed, first, normalized_status, side, values, with_direction

ALGORITHM_ID = "edwards_magee_defensive_exit"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "side",
    "em_defensive_adverse_signal",
    "em_defensive_signal_confirmed",
    "em_defensive_reversal_break_confirmed",
    "em_defensive_reversal_pattern",
    "em_data_provenance",
)

_ADVERSE_SIGNALS = {
    "adverse breakout",
    "adverse breakaway gap",
    "basic trendline break",
    "clear support penetration",
    "clear resistance penetration",
    "island after favorable move",
    "new minor high",
    "new minor low",
    "trendline penetration",
}
_REVERSAL_PATTERNS = {
    "diamond",
    "double top",
    "double bottom",
    "flag",
    "head and shoulders",
    "rectangle",
    "symmetrical triangle",
    "wedge",
}


def _observed_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "confirmed", "observed", "present"}:
        return True
    if label in {"false", "no", "unconfirmed", "absent", "none", "not present"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    candidate_side = side(state)
    adverse_signal = normalized_status(first(state, "em_defensive_adverse_signal"))
    if candidate_side not in {"BUY", "SELL"} or adverse_signal not in _ADVERSE_SIGNALS:
        result["edwards_magee_defensive_action"] = "INVALID_ADVERSE_SIGNAL"
        result["reasons"] = ["the current side and adverse signal must be an explicit source-described defensive event"]
        return result
    if not (first(state, "em_defensive_signal_confirmed") is True or explicitly_confirmed(first(state, "em_defensive_signal_confirmed"))):
        result["edwards_magee_defensive_action"] = "WAIT_FOR_CONFIRMATION"
        result["reasons"] = ["a suspected weakness is not enough to exit until the adverse signal is explicitly confirmed"]
        return result

    reversal_confirmed = _observed_bool(first(state, "em_defensive_reversal_break_confirmed"))
    reversal_pattern = normalized_status(first(state, "em_defensive_reversal_pattern"))
    if reversal_confirmed is None:
        result["edwards_magee_defensive_action"] = "INVALID_REVERSAL_INPUT"
        result["reasons"] = ["reversal confirmation must be an explicit boolean observation"]
        return result
    if not reversal_confirmed:
        result["edwards_magee_defensive_action"] = "EXIT_CURRENT_COMMITMENT"
        result["edwards_magee_reverse_candidate"] = False
        result["reasons"] = ["the source separates exiting a failed commitment from automatically entering the opposite side"]
        return result
    if reversal_pattern not in _REVERSAL_PATTERNS:
        result["edwards_magee_defensive_action"] = "REVERSAL_PATTERN_NOT_CONFIRMED"
        result["edwards_magee_reverse_candidate"] = False
        result["reasons"] = ["an opposite entry requires a confirmed reversal pattern, not merely an adverse trend signal"]
        return result

    result["edwards_magee_defensive_action"] = "EXIT_AND_REVERSE_CANDIDATE"
    result["edwards_magee_reverse_candidate"] = True
    return with_direction(
        result,
        state,
        "SELL" if candidate_side == "BUY" else "BUY",
        "the adverse breakout and confirmed reversal pattern support a separate opposite-side research candidate",
    )
