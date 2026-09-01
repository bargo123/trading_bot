"""Jeremy du Plessis' objective 45-degree Point-and-Figure trendline rule."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_45_degree_trendline"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 178-180"
KEYS = (
    "pf_45_trend_direction",
    "pf_45_reversal_boxes",
    "pf_45_thrust_boxes",
    "pf_45_break_direction",
    "pf_45_break_confirmed",
    "pf_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pf_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "pf_45_trend_direction"))
    break_direction = normalized_status(first(state, "pf_45_break_direction"))
    reversal = number(first(state, "pf_45_reversal_boxes"))
    thrust = number(first(state, "pf_45_thrust_boxes"))
    if trend not in {"up", "down"} or break_direction not in {"above", "below"}:
        result["view"] = "WAIT"
        result["reasons"] = ["45-degree trend and break directions must be explicit"]
        return result
    if reversal is None or reversal <= 0 or reversal != int(reversal) or thrust is None or thrust <= 0 or thrust != int(thrust):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["positive_reversal_and_thrust_boxes"]
        result["reasons"] = ["45-degree maintenance requires measured whole-box reversal and thrust sizes"]
        return result
    required = int(reversal + 2)
    result["pf_45_required_thrust_boxes"] = required
    if thrust < required:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed thrust is too weak to maintain the source 45-degree trend"]
        return result
    if not _truthy(first(state, "pf_45_break_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the 45-degree trendline break is not confirmed"]
        return result
    if trend == "up" and break_direction == "below":
        return with_direction(result, state, "SELL", "confirmed break below the objective bullish 45-degree line")
    if trend == "down" and break_direction == "above":
        return with_direction(result, state, "BUY", "confirmed break above the objective bearish 45-degree line")
    result["view"] = "WAIT"
    result["reasons"] = ["45-degree break direction does not contradict the prior trend"]
    return result
