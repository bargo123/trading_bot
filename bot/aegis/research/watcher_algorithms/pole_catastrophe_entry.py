"""Pole's duration-calibrated catastrophe-reversal entry perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "pole_catastrophe_entry"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_catastrophe_build_direction",
    "pole_catastrophe_precursor_duration",
    "pole_catastrophe_duration_p80",
    "pole_catastrophe_precursor_confirmed",
    "pole_catastrophe_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_catastrophe_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("pole_catastrophe_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = True
    build_direction = normalized_status(first(state, "pole_catastrophe_build_direction"))
    duration = number(first(state, "pole_catastrophe_precursor_duration"))
    duration_p80 = number(first(state, "pole_catastrophe_duration_p80"))
    if build_direction not in {"up", "down"}:
        result["pole_catastrophe_entry_action"] = "INVALID_BUILD_DIRECTION"
        result["reasons"] = ["catastrophe precursor direction must be an observed up or down state"]
        return result
    if duration is None or duration_p80 is None or duration < 0 or duration_p80 <= 0:
        result["pole_catastrophe_entry_action"] = "INVALID_DURATION_INPUT"
        result["reasons"] = ["catastrophe entry needs a finite non-negative duration and positive observed 80th percentile"]
        return result

    reversal_side = "SELL" if build_direction == "up" else "BUY"
    ratio = duration / duration_p80
    result.update(
        {
            "pole_catastrophe_build_direction": build_direction.upper(),
            "pole_catastrophe_precursor_duration": duration,
            "pole_catastrophe_duration_p80": duration_p80,
            "pole_catastrophe_duration_ratio": ratio,
            "pole_catastrophe_reversal_side": reversal_side,
        }
    )
    if not explicitly_confirmed(first(state, "pole_catastrophe_precursor_confirmed")):
        result["pole_catastrophe_entry_action"] = "WAIT_FOR_PRECURSOR_CONFIRMATION"
        result["reasons"] = ["the precursor trend has not been explicitly confirmed"]
        return result
    if duration < duration_p80:
        result["pole_catastrophe_entry_action"] = "WAIT_FOR_EIGHTIETH_PERCENTILE"
        result["reasons"] = ["observed precursor duration has not reached the calibrated 80th-percentile timing point"]
        return result

    result["pole_catastrophe_entry_action"] = "REVERSAL_ALERT"
    result["warnings"] = [
        "duration timing is a research alert for a fast reversal; it is not a guaranteed price forecast"
    ]
    return with_direction(
        result,
        state,
        reversal_side,
        "observed catastrophe precursor reached the calibrated 80th-percentile duration",
    )
