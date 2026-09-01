"""Volume-weighted price context using only explicitly labelled tick volume."""
from __future__ import annotations

from ._common import base, explicitly_observed, strings, values, with_direction

ALGORITHM_ID = "vwap_context"
SOURCES = (
    "Anna Coulling — A Complete Guide to Volume Price Analysis",
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
)
KEYS = ("vwap_proxy", "vwap_relation", "vwap_data_provenance", "volume_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("volume_weighted_price",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["warnings"] = ["tick_volume_proxy_is_not_real_traded_volume"]
    provenance = strings(state, "vwap_data_provenance")
    if not explicitly_observed(provenance, accepted=("real", "volume", "traded")):
        result["view"] = "WAIT"
        result["reasons"] = ["VWAP direction requires real traded-volume provenance"]
        return result
    relation = strings(state, "vwap_relation")
    if relation == "above_vwap":
        return with_direction(result, state, "BUY", "price is above the tick-volume-weighted price proxy")
    if relation == "below_vwap":
        return with_direction(result, state, "SELL", "price is below the tick-volume-weighted price proxy")
    result["view"] = "WAIT"
    result["reasons"] = ["price is at the tick-volume-weighted price proxy"]
    return result
