"""Link's cancel-if-close stop-discipline check (High Probability Trading, ch. 9)."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "link_stop_discipline"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_stop_initial_distance",
    "link_stop_current_distance",
    "link_stop_moved_away",
    "link_stop_discipline_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_stop_discipline_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_stop_discipline_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    initial = number(first(state, "link_stop_initial_distance"))
    current = number(first(state, "link_stop_current_distance"))
    moved_away = first(state, "link_stop_moved_away")
    if initial is None or current is None or initial <= 0.0 or current <= 0.0 or not isinstance(moved_away, bool):
        result["link_stop_discipline_assessment"] = "INVALID_STOP_INPUT"
        result["reasons"] = ["initial/current stop distances must be positive and stop movement must be an explicit boolean"]
        return result

    result.update({
        "link_stop_initial_distance": initial,
        "link_stop_current_distance": current,
        "link_stop_distance_delta": current - initial,
        "directional_claim": False,
    })
    if moved_away or current > initial:
        result["link_stop_discipline_assessment"] = "CANCEL_IF_CLOSE_VIOLATION"
        result["reasons"] = ["the stop was widened or moved farther away after entry; the source warns against cancelling protection to avoid a loss"]
    else:
        result["link_stop_discipline_assessment"] = "STOP_PROTECTION_INTACT"
        result["reasons"] = ["the stop was not moved farther from the entry"]
    return result
