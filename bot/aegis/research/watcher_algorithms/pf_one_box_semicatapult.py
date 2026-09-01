"""Jeremy du Plessis' one-box Point-and-Figure semi-catapult perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_one_box_semicatapult"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 116-122"
KEYS = (
    "pf_box_reversal",
    "pf_pattern_type",
    "pf_trend",
    "pf_initial_move_confirmed",
    "pf_pullback_confirmed",
    "pf_breakout_confirmed",
    "pf_breakout_direction",
    "pf_white_space_boxes",
    "pf_pattern_width_columns",
    "pf_data_provenance",
)


def _truthy(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_point_and_figure_chart"]
        result["reasons"] = ["semi-catapult analysis requires observed Point-and-Figure chart provenance"]
        return result
    if normalized_status(first(state, "pf_box_reversal")) != "1 box":
        result["view"] = "WAIT"
        result["reasons"] = ["a semi-catapult is the one-box continuation pattern in this perspective"]
        return result
    if normalized_status(first(state, "pf_pattern_type")).replace(" ", "_") not in {"semi_catapult", "semicatapult"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed one-box pattern is not a semi-catapult"]
        return result

    trend = normalized_status(first(state, "pf_trend"))
    breakout_direction = normalized_status(first(state, "pf_breakout_direction"))
    if trend not in {"up", "down"} or breakout_direction not in {"up", "down"} or breakout_direction != trend:
        result["view"] = "WAIT"
        result["reasons"] = ["a continuation semi-catapult requires an explicit breakout in the established trend direction"]
        return result
    white_space = number(first(state, "pf_white_space_boxes"))
    width = number(first(state, "pf_pattern_width_columns"))
    if white_space is None or white_space <= 0 or not white_space.is_integer() or width is None or width <= 0 or not width.is_integer():
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["positive_white_space_and_pattern_width"]
        result["reasons"] = ["semi-catapult strength requires finite observed white-space and pattern-width boxes"]
        return result
    if not _truthy(first(state, "pf_initial_move_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the advance into the one-box pattern is not confirmed"]
        return result
    if not _truthy(first(state, "pf_pullback_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the initial advance has not been followed by the required pullback"]
        return result
    if not _truthy(first(state, "pf_breakout_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the semi-catapult has not broken beyond the prior resistance/support column"]
        return result

    result["pf_semicatapult_white_space_boxes"] = int(white_space)
    result["pf_semicatapult_pattern_width_columns"] = int(width)
    result["pf_semicatapult_assessment"] = "CONFIRMED_WITH_WHITE_SPACE"
    return with_direction(
        result,
        state,
        "BUY" if trend == "up" else "SELL",
        "the one-box semi-catapult has an advance, pullback, and confirmed trend breakout",
    )
