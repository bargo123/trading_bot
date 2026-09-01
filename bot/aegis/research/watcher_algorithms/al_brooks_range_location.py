"""Trading-range location filter from Al Brooks.

The range middle is a poor location for a directional scalp; the edges are
where a separate rejection/fade hypothesis can be studied. This module only
classifies location and never emits BUY or SELL authority.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "al_brooks_range_location"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "range_state",
    "range_location",
    "range_location_provenance",
    "range_location_confirmation",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_range_location",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    range_state = normalized_status(first(state, "range_state"))
    location = normalized_status(first(state, "range_location"))
    provenance = normalized_status(first(state, "range_location_provenance"))
    confirmation = normalized_status(first(state, "range_location_confirmation"))
    if "range" not in range_state or not location or not provenance or not confirmation:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_range_location"]
        result["reasons"] = ["range location requires an explicitly observed range, location, and confirmation"]
        return result
    if any(token in provenance for token in ("synthetic", "proxy", "unverified", "unknown")):
        result["range_location_assessment"] = "UNKNOWN"
        result["warnings"] = ["range location provenance is synthetic, proxy, or unverified"]
        result["reasons"] = ["range location cannot be classified from proxy structure"]
        return result
    if not any(token in confirmation for token in ("observed", "confirmed", "validated")):
        result["range_location_assessment"] = "UNKNOWN"
        result["reasons"] = ["range location is not explicitly confirmed"]
        return result
    if any(token in location for token in ("middle", "center", "midpoint")):
        result["range_location_assessment"] = "MIDDLE"
        result["warnings"] = ["middle-of-range entries have poor directional location"]
        result["reasons"] = ["the copied state is in the range middle, not at a studied edge"]
    elif any(token in location for token in ("upper", "lower", "edge", "high", "low")):
        result["range_location_assessment"] = "EDGE"
        result["reasons"] = ["the copied state is at an observed range edge for a separate rejection/fade study"]
    else:
        result["range_location_assessment"] = "UNKNOWN"
        result["reasons"] = ["range location label is not recognized"]
    return result
