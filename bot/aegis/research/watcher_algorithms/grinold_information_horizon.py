"""Grinold-Kahn information-horizon and signal-decay diagnostic."""
from __future__ import annotations

import math

from ._common import absent, base, first, number, explicitly_observed, values

ALGORITHM_ID = "grinold_information_horizon"
SOURCES = ("Richard Grinold and Ronald Kahn — Active Portfolio Management",)
KEYS = (
    "grinold_signal_half_life_s",
    "grinold_signal_age_s",
    "grinold_holding_horizon_s",
    "grinold_information_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_signal_age_and_half_life",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    half_life = number(first(state, "grinold_signal_half_life_s"))
    age = number(first(state, "grinold_signal_age_s"))
    holding_horizon = number(first(state, "grinold_holding_horizon_s"))
    provenance = first(state, "grinold_information_data_provenance")
    if half_life is None or age is None or holding_horizon is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_signal_half_life_age_and_holding_horizon"]
        return result
    if half_life <= 0 or age < 0 or holding_horizon <= 0:
        result["grinold_horizon_assessment"] = "INVALID_HORIZON_INPUT"
        result["reasons"] = ["half-life and holding horizon must be positive and signal age non-negative"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["grinold_information_data_provenance"]
        return result

    result["grinold_decay_weight"] = math.pow(0.5, age / half_life)
    result["grinold_signal_age_s"] = age
    result["grinold_signal_half_life_s"] = half_life
    result["grinold_holding_horizon_s"] = holding_horizon
    result["directional_claim"] = False
    if age > holding_horizon:
        result["grinold_horizon_assessment"] = "STALE_INFORMATION"
        result["reasons"] = ["signal age exceeds the declared holding horizon"]
    else:
        result["grinold_horizon_assessment"] = "IN_HORIZON"
        result["reasons"] = ["signal age is within the declared holding horizon and decay is measured explicitly"]
    return result
