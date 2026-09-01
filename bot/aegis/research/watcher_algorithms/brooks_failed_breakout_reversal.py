"""Al Brooks failed-breakout reversal toward the range middle perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction
from ._deprado_common import provenance_ok

ALGORITHM_ID = "brooks_failed_breakout_reversal"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_failed_breakout_detected",
    "brooks_failed_breakout_original_direction",
    "brooks_failed_breakout_reversal_confirmed",
    "brooks_failed_breakout_point",
    "brooks_current_price",
    "brooks_failed_breakout_range_midpoint",
    "brooks_failed_breakout_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = str(value or "").strip().lower().replace("_", " ")
    if label in {"true", "yes", "observed", "confirmed", "present"}:
        return True
    if label in {"false", "no", "absent", "not confirmed"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    detected = _boolean(first(state, "brooks_failed_breakout_detected"))
    confirmed = _boolean(first(state, "brooks_failed_breakout_reversal_confirmed"))
    original = str(first(state, "brooks_failed_breakout_original_direction") or "").strip().upper()
    point = number(first(state, "brooks_failed_breakout_point"))
    current = number(first(state, "brooks_current_price"))
    midpoint = number(first(state, "brooks_failed_breakout_range_midpoint"))
    missing = [
        key for key, value in (
            ("brooks_failed_breakout_detected", detected),
            ("brooks_failed_breakout_original_direction", original if original in {"BUY", "SELL"} else None),
            ("brooks_failed_breakout_reversal_confirmed", confirmed),
            ("brooks_failed_breakout_point", point),
            ("brooks_current_price", current),
            ("brooks_failed_breakout_range_midpoint", midpoint),
        ) if value is None
    ]
    provenance = first(state, "brooks_failed_breakout_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("brooks_failed_breakout_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["analysis_stage"] = "causal_failed_breakout_reversal"
    result["directional_claim"] = False
    if not detected or not confirmed:
        result["brooks_failed_breakout_assessment"] = "FAILURE_NOT_CONFIRMED"
        result["reasons"] = ["a reversal is not inferred without an observed failed break and confirmation"]
        return result
    failed = current < point if original == "BUY" else current > point
    if not failed:
        result["brooks_failed_breakout_assessment"] = "BREAKOUT_NOT_FAILED"
        result["reasons"] = ["current price has not returned through the original breakout point"]
        return result
    target_distance = abs(current - midpoint)
    if target_distance <= 0:
        result["brooks_failed_breakout_assessment"] = "NO_RANGE_MIDDLE_ROOM"
        result["reasons"] = ["the observed price is already at the recorded range midpoint"]
        return result
    reversal = "SELL" if original == "BUY" else "BUY"
    result["brooks_failed_breakout_assessment"] = "CONFIRMED_FAILED_BREAKOUT_REVERSAL"
    result["brooks_failed_breakout_target_distance"] = target_distance
    result["warnings"] = ["failed-breakout reversal is a research perspective; midpoint is an observed hypothesis target"]
    result["directional_claim"] = True
    return with_direction(result, state, reversal, "the breakout failed and the confirmed reversal points back toward the range middle")
