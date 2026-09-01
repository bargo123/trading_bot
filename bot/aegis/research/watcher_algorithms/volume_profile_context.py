"""Volume-profile value/acceptance perspective requiring real volume data."""
from __future__ import annotations

from ._common import base, direction, explicitly_observed, first, strings, text, values, with_direction

ALGORITHM_ID = "volume_profile_context"
SOURCES = (
    "Markets in Profile — James Dalton, Robert Dalton, Eric Jones",
    "Mind Over Markets — James Dalton, Eric Jones, Robert Dalton",
    "A Complete Guide to Volume Price Analysis — Anna Coulling",
)
KEYS = ("volume_profile", "volume_profile_state", "volume_profile_direction", "volume_profile_data_provenance", "poc", "vah", "val")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("real_volume_profile",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    profile = first(state, "volume_profile")
    source = text(first(state, "volume_profile_data_provenance"))
    if isinstance(profile, dict):
        source = source or text(profile.get("source"))
    source_lower = source.lower()
    if not explicitly_observed(source, accepted=("real", "volume", "traded")) or any(token in source_lower for token in ("tick", "quote")):
        result["view"] = "WAIT"
        result["warnings"] = ["tick-price profile is not a real volume profile"]
        result["reasons"] = ["real traded-volume provenance is not established"]
        return result
    text_value = strings(state, "volume_profile_state", "volume_profile_direction")
    signal = direction(text_value)
    if signal:
        return with_direction(result, state, signal, "real volume-profile state has a directional value/acceptance signal")
    result["view"] = "WAIT"
    result["reasons"] = ["real volume profile is available but its value interaction has no direction"]
    return result
