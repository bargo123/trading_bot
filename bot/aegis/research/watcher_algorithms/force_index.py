"""Elder Force Index perspective using an explicitly supplied force measure."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, number, strings, values, with_direction

ALGORITHM_ID = "force_index"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = ("force_index", "force_index_direction", "force_index_confirmation", "force_index_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("force_index_measure",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    force = number(first(state, "force_index"))
    direction_text = strings(state, "force_index_direction")
    confirmed = explicitly_confirmed(first(state, "force_index_confirmation"))
    provenance = first(state, "force_index_data_provenance")
    if force is None or not confirmed or not explicitly_observed(provenance, accepted=("real", "volume", "traded")):
        result["view"] = "WAIT"
        result["reasons"] = ["Force Index requires a numeric measure, real-volume provenance, and explicit confirmation"]
        return result
    if force > 0 and "up" in direction_text:
        return with_direction(result, state, "BUY", "positive confirmed Force Index supports upside pressure")
    if force < 0 and "down" in direction_text:
        return with_direction(result, state, "SELL", "negative confirmed Force Index supports downside pressure")
    result["view"] = "WAIT"
    result["reasons"] = ["Force Index sign and recorded direction do not agree"]
    return result
