"""Macro/fundamental perspective requiring verified external observations."""
from __future__ import annotations

from ._common import base, direction, explicitly_observed, explicitly_validated, first, strings, text, values, with_direction

ALGORITHM_ID = "fundamental_macro"
SOURCES = (
    "Day Trading and Swing Trading the Currency Market — Kathy Lien",
    "The Economics of Financial Markets — Roy E. Bailey",
    "The New Trading for a Living — Alexander Elder",
)
KEYS = ("macro_bias", "macro_event_risk", "macro_confirmation", "macro_data_provenance", "interest_rate_differential", "economic_surprise")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("verified_macro_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = text(first(state, "macro_data_provenance")).lower()
    if not explicitly_observed(provenance, accepted=("verified", "official", "timestamped")):
        result["view"] = "WAIT"
        result["warnings"] = ["macro direction requires verified timestamped data"]
        result["reasons"] = ["macro provenance is absent or unverified"]
        return result
    event = strings(state, "macro_event_risk")
    if any(token in event for token in ("imminent", "high", "unknown", "conflict")):
        result["view"] = "WAIT"
        result["reasons"] = ["macro event risk prevents a clean directional interpretation"]
        return result
    confirmation = first(state, "macro_confirmation")
    if not explicitly_validated(confirmation, accepted=("confirmed", "validated", "observed")):
        result["view"] = "WAIT"
        result["reasons"] = ["macro bias is not confirmed"]
        return result
    signal = direction(strings(state, "macro_bias"))
    if signal:
        return with_direction(result, state, signal, "verified macro bias has directional confirmation")
    result["view"] = "WAIT"
    result["reasons"] = ["verified macro inputs have no unambiguous directional bias"]
    return result
