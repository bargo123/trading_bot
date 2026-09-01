"""Chan's mean-reversion half-life and horizon compatibility diagnostic."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "chan_mean_reversion_half_life"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_mean_reversion_coefficient",
    "chan_mean_reversion_half_life",
    "chan_mean_reversion_horizon",
    "chan_half_life_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    coefficient = number(first(state, "chan_mean_reversion_coefficient"))
    half_life = number(first(state, "chan_mean_reversion_half_life"))
    horizon = number(first(state, "chan_mean_reversion_horizon"))
    missing = [
        key for key, value in (
            ("chan_mean_reversion_coefficient", coefficient),
            ("chan_mean_reversion_half_life", half_life),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "chan_half_life_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("chan_half_life_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if half_life <= 0 or (horizon is not None and horizon <= 0):
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["half-life and declared horizon must be positive"]
        return result
    result["chan_implied_half_life"] = -math.log(2.0) / coefficient if coefficient < 0 else None
    result["chan_mean_reversion_half_life"] = half_life
    if horizon is not None:
        result["chan_mean_reversion_horizon"] = horizon
    if coefficient >= 0:
        result["chan_half_life_assessment"] = "NON_MEAN_REVERTING"
        result["reasons"] = ["the level coefficient is not negative, so no mean-reversion half-life is implied"]
    elif horizon is None:
        result["chan_half_life_assessment"] = "HORIZON_NOT_DECLARED"
        result["reasons"] = ["half-life is measured, but no declared trading horizon was supplied for comparison"]
    elif half_life <= horizon:
        result["chan_half_life_assessment"] = "PRACTICAL_FOR_HORIZON"
        result["reasons"] = ["the observed reversion half-life fits within the declared trading horizon"]
    else:
        result["chan_half_life_assessment"] = "TOO_SLOW_FOR_HORIZON"
        result["reasons"] = ["the observed reversion half-life exceeds the declared trading horizon"]
    return result
