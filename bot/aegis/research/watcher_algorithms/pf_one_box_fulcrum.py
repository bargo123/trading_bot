"""Jeremy du Plessis' one-box Point-and-Figure fulcrum perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "pf_one_box_fulcrum"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 119-125, 137-143"
KEYS = (
    "pf_box_reversal",
    "pf_pattern_type",
    "pf_fulcrum_direction",
    "pf_move_into_pattern_confirmed",
    "pf_move_out_pattern_confirmed",
    "pf_catapult_breakout_confirmed",
    "pf_catapult_breakout_direction",
    "pf_exit_structure",
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
        result["reasons"] = ["fulcrum analysis requires observed Point-and-Figure chart provenance"]
        return result
    if normalized_status(first(state, "pf_box_reversal")) != "1 box":
        result["view"] = "WAIT"
        result["reasons"] = ["a fulcrum is evaluated here on the one-box reversal chart"]
        return result
    if normalized_status(first(state, "pf_pattern_type")) != "fulcrum":
        result["view"] = "WAIT"
        result["reasons"] = ["the observed one-box pattern is not a fulcrum"]
        return result

    direction = normalized_status(first(state, "pf_fulcrum_direction"))
    breakout_direction = normalized_status(first(state, "pf_catapult_breakout_direction"))
    exit_structure = normalized_status(first(state, "pf_exit_structure")).replace(" ", "_")
    expected_structure = "rising_bottoms" if direction == "up" else "falling_tops" if direction == "down" else ""
    if direction not in {"up", "down"} or breakout_direction != direction:
        result["view"] = "WAIT"
        result["reasons"] = ["fulcrum and catapult breakout directions must be explicit and agree"]
        return result
    if exit_structure != expected_structure:
        result["view"] = "WAIT"
        result["reasons"] = ["the fulcrum exit must show rising bottoms for an upside reversal or falling tops for a downside reversal"]
        return result
    if not _truthy(first(state, "pf_move_into_pattern_confirmed")) or not _truthy(first(state, "pf_move_out_pattern_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["a fulcrum requires a confirmed move into and a confirmed move out of the pattern"]
        return result
    if not _truthy(first(state, "pf_catapult_breakout_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the fulcrum catapult point has not been broken and confirmed"]
        return result

    result["pf_fulcrum_assessment"] = "CONFIRMED_REVERSAL"
    return with_direction(
        result,
        state,
        "BUY" if direction == "up" else "SELL",
        "the one-box fulcrum has a confirmed reversal structure and catapult breakout",
    )
