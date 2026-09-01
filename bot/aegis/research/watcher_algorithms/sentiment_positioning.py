"""Sentiment/positioning perspective requiring verified positioning data."""
from __future__ import annotations

from ._common import base, direction, explicitly_observed, explicitly_validated, first, number, strings, text, values, with_direction

ALGORITHM_ID = "sentiment_positioning"
SOURCES = (
    "Day Trading and Swing Trading the Currency Market — Kathy Lien",
    "Active Portfolio Management — Grinold and Kahn",
    "The Economics of Financial Markets — Roy E. Bailey",
)
KEYS = ("sentiment_bias", "positioning_bias", "sentiment_confirmation", "sentiment_data_provenance", "sentiment_sample_n", "crowding")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("verified_sentiment_positioning",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = text(first(state, "sentiment_data_provenance")).lower()
    sample = number(first(state, "sentiment_sample_n"))
    if not explicitly_observed(provenance, accepted=("verified", "official", "timestamped")):
        result["view"] = "WAIT"
        result["warnings"] = ["sentiment/positioning must be sourced from verified observations"]
        result["reasons"] = ["sentiment provenance is absent or unverified"]
        return result
    if sample is None or sample < 30:
        result["view"] = "WAIT"
        result["reasons"] = ["positioning sample is too small for a research perspective"]
        return result
    confirmation = first(state, "sentiment_confirmation")
    if not explicitly_validated(confirmation, accepted=("confirmed", "validated", "observed")):
        result["view"] = "WAIT"
        result["reasons"] = ["sentiment/positioning signal lacks confirmation"]
        return result
    crowding = strings(state, "crowding", "positioning_bias")
    if any(token in crowding for token in ("extreme_long", "crowded_long", "overlong")):
        return with_direction(result, state, "SELL", "extreme long positioning is treated as a contrarian warning")
    if any(token in crowding for token in ("extreme_short", "crowded_short", "overshort")):
        return with_direction(result, state, "BUY", "extreme short positioning is treated as a contrarian warning")
    signal = direction(strings(state, "sentiment_bias", "positioning_bias"))
    if signal:
        return with_direction(result, state, signal, "verified positioning has directional confirmation")
    result["view"] = "WAIT"
    result["reasons"] = ["verified positioning has no unambiguous directional interpretation"]
    return result
