"""On-balance-volume context using explicitly labelled tick-volume proxy."""
from __future__ import annotations

from ._common import base, explicitly_observed, strings, values, with_direction

ALGORITHM_ID = "obv_volume"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Anna Coulling — A Complete Guide to Volume Price Analysis",
)
KEYS = ("obv_proxy", "obv_direction", "obv_data_provenance", "volume_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("on_balance_volume",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["warnings"] = ["tick_volume_proxy_is_not_real_traded_volume"]
    provenance = strings(state, "obv_data_provenance")
    if not explicitly_observed(provenance, accepted=("real", "volume", "traded")):
        result["view"] = "WAIT"
        result["reasons"] = ["OBV direction requires real traded-volume provenance"]
        return result
    direction = strings(state, "obv_direction")
    if direction == "up":
        return with_direction(result, state, "BUY", "signed tick-volume proxy is increasing with price observations")
    if direction == "down":
        return with_direction(result, state, "SELL", "signed tick-volume proxy is decreasing with price observations")
    result["view"] = "WAIT"
    result["reasons"] = ["signed tick-volume proxy has no resolved direction"]
    return result
