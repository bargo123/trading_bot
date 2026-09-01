"""Murphy speed-resistance-line (speedline) perspective.

Speedlines measure the observed rate of ascent/descent with one-third and
two-thirds divisions.  A line hold can support continuation, while a broken
line is treated as a warning/retest context rather than an automatic reversal.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "murphy_speed_resistance_lines"
SOURCES = ("John J. Murphy — Technical Analysis of the Financial Markets",)
KEYS = (
    "murphy_speedline_trend",
    "murphy_speedline_one_third_price",
    "murphy_speedline_two_thirds_price",
    "murphy_speedline_current_price",
    "murphy_speedline_location",
    "murphy_speedline_reaction",
    "murphy_speedline_reaction_direction",
    "murphy_speedline_reaction_confirmed",
    "murphy_speedline_data_provenance",
)
VALID_LOCATIONS = {
    "above_two_thirds",
    "between_speedlines",
    "below_one_third",
    "broken_above_two_thirds",
    "broken_below_one_third",
    "reclaimed",
}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not explicitly_observed(
        first(state, "murphy_speedline_data_provenance"),
        accepted=("observed completed quote bars", "observed price bars", "real price"),
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_speedline_data"]
        result["reasons"] = ["speed-resistance lines require observed completed price-bar provenance"]
        return result

    trend = normalized_status(first(state, "murphy_speedline_trend"))
    reaction = normalized_status(first(state, "murphy_speedline_reaction")).replace(" ", "_")
    reaction_direction = normalized_status(first(state, "murphy_speedline_reaction_direction"))
    location = normalized_status(first(state, "murphy_speedline_location")).replace(" ", "_")
    one_third = number(first(state, "murphy_speedline_one_third_price"))
    two_thirds = number(first(state, "murphy_speedline_two_thirds_price"))
    current = number(first(state, "murphy_speedline_current_price"))
    confirmed = volman_truth(first(state, "murphy_speedline_reaction_confirmed"))
    if trend not in {"up", "down"} or reaction_direction not in {"up", "down"} or reaction not in {"support_hold", "resistance_hold", "reclaimed", "broken"}:
        result["view"] = "WAIT"
        result["reasons"] = ["speedline trend, line reaction, and reaction direction must be explicit observations"]
        return result
    if None in (one_third, two_thirds, current) or one_third == two_thirds:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_speedline_prices"]
        result["reasons"] = ["both speedline levels and the current price must be finite and distinct"]
        return result
    if not location:
        result["view"] = "WAIT"
        result["reasons"] = ["current relation to the one-third and two-thirds lines is not observed"]
        return result
    if location not in VALID_LOCATIONS:
        result["view"] = "WAIT"
        result["reasons"] = ["current relation to the speedlines is not a recognized observed state"]
        return result
    if reaction == "broken" or "broken" in location:
        result["speedline_assessment"] = "BROKEN_LINE_WAIT"
        result["view"] = "WAIT"
        result["reasons"] = ["a broken speedline is a warning/retest context, not an automatic reversal signal"]
        return result
    if not confirmed or reaction_direction != trend:
        result["speedline_assessment"] = "LINE_HOLD_UNCONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["speedline reaction is not confirmed in the trend direction"]
        return result

    result["speedline_assessment"] = (
        "SPEEDLINE_SUPPORT_HOLD" if reaction == "support_hold" or trend == "up" else "SPEEDLINE_RESISTANCE_HOLD"
    )
    return with_direction(
        result,
        state,
        "BUY" if trend == "up" else "SELL",
        "the observed one-third/two-thirds speedline held and the confirmed reaction follows the trend",
    )
