"""Dalton/Steidlmayer Market Profile day-structure classification."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "dalton_day_structure"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Peter Steidlmayer — Steidlmayer on Markets",
)
SOURCE_PAGES = "pp. 60-64, 76-80"
KEYS = (
    "dalton_day_type",
    "dalton_day_direction",
    "dalton_initial_balance_range",
    "dalton_range_extension",
    "dalton_close_location_percent",
    "dalton_extension_sides",
    "dalton_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "dalton_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("dalton_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    day_type = normalized_status(first(state, "dalton_day_type"))
    allowed = {
        "nontrend", "nontrend day", "normal", "normal day", "normal variation", "normal variation day",
        "trend", "trend day", "neutral", "neutral day", "running profile neutral", "running profile neutral day",
    }
    initial_range = number(first(state, "dalton_initial_balance_range"))
    extension = number(first(state, "dalton_range_extension"))
    close_location = number(first(state, "dalton_close_location_percent"))
    if day_type not in allowed:
        result["view"] = "WAIT"
        result["reasons"] = ["the supplied day structure is not one of the source's observed profile classifications"]
        return result
    if initial_range is None or initial_range <= 0 or extension is None or extension < 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["positive_initial_balance_and_nonnegative_extension"]
        return result
    if close_location is None or not 0.0 <= close_location <= 100.0:
        result["view"] = "WAIT"
        result["reasons"] = ["day-structure classification requires a finite close-location percentage"]
        return result
    result.update({
        "dalton_day_structure_classification": day_type.upper().replace(" ", "_"),
        "dalton_extension_ratio": extension / initial_range,
        "dalton_day_direction": normalized_status(first(state, "dalton_day_direction")),
        "dalton_extension_sides": normalized_status(first(state, "dalton_extension_sides")),
    })
    result["view"] = "WAIT"
    result["reasons"] = ["the observed Market Profile day type is contextual evidence, not a standalone entry signal"]
    return result
