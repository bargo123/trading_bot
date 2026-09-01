"""Market-profile value/auction and initiative algorithm."""
from __future__ import annotations
from ._common import base, direction, strings, values, with_direction

ALGORITHM_ID = "market_profile_auction"
SOURCES = ("James Dalton — Markets in Profile", "James Dalton — Mind Over Markets", "Frank de Jong — The Microstructure of Financial Markets")
KEYS = ("market_profile", "value_area", "poc", "opening_drive", "opening_type", "auction_state", "balance", "initiative")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("auction_or_profile_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    profile = state.get("market_profile")
    if isinstance(profile, dict) and profile.get("source") == "tick_price_profile_proxy":
        result["warnings"] = ["tick_price_profile_proxy is not a volume profile; auction conclusions are provisional"]
        result["view"] = "WAIT"
        result["reasons"] = ["auction direction requires real volume-at-price provenance"]
        return result
    if "balance" in text or "auction" in text:
        result["view"] = "WAIT"
        result["reasons"] = ["market-generated information indicates a balanced auction"]
        return result
    signal = direction(text)
    if signal:
        return with_direction(result, state, signal, "profile records initiative or opening-drive direction")
    result["view"] = "WAIT"
    result["reasons"] = ["profile is available but initiative direction is unresolved"]
    return result
