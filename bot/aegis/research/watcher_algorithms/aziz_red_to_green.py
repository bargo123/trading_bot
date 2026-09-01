"""Andrew Aziz's previous-close Red-to-Green / Green-to-Red perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "aziz_red_to_green"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_rtg_transition",
    "aziz_rtg_previous_close",
    "aziz_rtg_moving_toward_level",
    "aziz_rtg_volume_confirmation",
    "aziz_rtg_stop_defined",
    "aziz_rtg_target_defined",
    "aziz_rtg_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_rtg_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("aziz_rtg_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if number(first(state, "aziz_rtg_previous_close")) is None:
        result["view"] = "WAIT"
        result["reasons"] = ["the previous-day close is not a valid observed level"]
        return result
    transition = normalized_status(first(state, "aziz_rtg_transition")).replace(" ", "_")
    expected_side = {"red_to_green": "BUY", "green_to_red": "SELL"}.get(transition)
    if expected_side is None:
        result["view"] = "WAIT"
        result["reasons"] = ["the previous-close transition is not Red-to-Green or Green-to-Red"]
        return result
    if str(first(state, "side") or "").upper() != expected_side:
        result["view"] = "WAIT"
        result["reasons"] = [f"the observed {transition} transition does not align with the candidate side"]
        return result
    checks = (
        ("aziz_rtg_moving_toward_level", "price is not moving toward the previous-day close"),
        ("aziz_rtg_volume_confirmation", "rising-volume confirmation is missing"),
        ("aziz_rtg_stop_defined", "the nearest technical invalidation is not defined"),
        ("aziz_rtg_target_defined", "the previous-close target is not defined"),
    )
    for key, reason in checks:
        if not volman_truth(first(state, key)):
            result["view"] = "WAIT"
            result["reasons"] = [reason]
            return result
    return with_direction(result, state, expected_side, f"{transition} is approaching the observed previous-day close with volume confirmation")
