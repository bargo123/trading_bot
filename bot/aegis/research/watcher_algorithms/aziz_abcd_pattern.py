"""Andrew Aziz's ABCD pullback-and-support perspective for the Watcher."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "aziz_abcd_pattern"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_abcd_impulse_direction",
    "aziz_abcd_point_b_confirmed",
    "aziz_abcd_point_c_support",
    "aziz_abcd_c_support_holds",
    "aziz_abcd_entry_near_c",
    "aziz_abcd_stop_defined",
    "aziz_abcd_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_abcd_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("aziz_abcd_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if str(first(state, "side") or "").upper() != "BUY":
        result["view"] = "WAIT"
        result["reasons"] = ["the source ABCD perspective is a long pullback setup"]
        return result
    if normalized_status(first(state, "aziz_abcd_impulse_direction")) not in {"up", "uptrend", "bullish"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the initial ABCD impulse is not upward"]
        return result
    if number(first(state, "aziz_abcd_point_c_support")) is None:
        result["view"] = "WAIT"
        result["reasons"] = ["point C does not contain an observed support level"]
        return result
    checks = (
        ("aziz_abcd_point_b_confirmed", "point B is not a confirmed impulse high"),
        ("aziz_abcd_c_support_holds", "point C support is not holding"),
        ("aziz_abcd_entry_near_c", "entry is not near the defined point C support"),
        ("aziz_abcd_stop_defined", "the point C invalidation stop is not defined"),
    )
    for key, reason in checks:
        if not volman_truth(first(state, key)):
            result["view"] = "WAIT"
            result["reasons"] = [reason]
            return result
    return with_direction(result, state, "BUY", "upward impulse has pulled back to a holding point C support with defined invalidation")
