"""Murphy percentage-retracement continuation perspective.

The rule treats roughly one-third to two-thirds as a normal correction, with
the 33--50 percent area as the preferred continuation reference.  It is a
contextual study and requires a causal reaction after the retracement; the
level alone is never a signal.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "murphy_percentage_retracement"
SOURCES = ("John J. Murphy — Technical Analysis of the Financial Markets",)
KEYS = (
    "murphy_retracement_trend",
    "murphy_retracement_percent",
    "murphy_retracement_reaction_direction",
    "murphy_retracement_reaction_confirmed",
    "murphy_retracement_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = normalized_status(first(state, "murphy_retracement_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_retracement_data"]
        result["reasons"] = ["percentage retracement requires observed completed price-bar provenance"]
        return result

    trend = normalized_status(first(state, "murphy_retracement_trend"))
    reaction = normalized_status(first(state, "murphy_retracement_reaction_direction"))
    retracement = number(first(state, "murphy_retracement_percent"))
    confirmed = volman_truth(first(state, "murphy_retracement_reaction_confirmed"))
    if trend not in {"up", "down"} or reaction not in {"up", "down"} or retracement is None:
        result["view"] = "WAIT"
        result["reasons"] = ["trend, retracement percentage, and reaction direction must be explicit observations"]
        return result
    if retracement < 33.0:
        result["retracement_assessment"] = "TOO_SHALLOW"
        result["view"] = "WAIT"
        result["reasons"] = ["the correction has not reached the source's approximate one-third reference"]
        return result
    if retracement > 66.0:
        result["retracement_assessment"] = "OUTSIDE_NORMAL_RANGE"
        result["view"] = "WAIT"
        result["reasons"] = ["the correction is deeper than the source's approximate two-thirds maximum"]
        return result
    if retracement > 50.0:
        result["retracement_assessment"] = "DEEP_BUT_WITHIN_NORMAL_RANGE"
        result["view"] = "WAIT"
        result["reasons"] = ["the correction is within the broad range but outside the preferred 33-50 percent zone"]
        return result
    if not confirmed or reaction != trend:
        result["retracement_assessment"] = "PREFERRED_ZONE_UNCONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the preferred retracement zone lacks a confirmed reaction in the trend direction"]
        return result

    result["retracement_assessment"] = "PREFERRED_CONTINUATION_ZONE"
    return with_direction(
        result,
        state,
        "BUY" if trend == "up" else "SELL",
        "the observed correction is in Murphy's preferred 33-50 percent continuation zone and reacted with the trend",
    )
