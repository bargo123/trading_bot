"""The 10XROI source's confirmed-breakout context perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "thomas_breakout_context"
SOURCES = ("The 10XROI Trading System",)
KEYS = (
    "side",
    "thomas_breakout_type",
    "thomas_breakout_direction",
    "thomas_breakout_confirmation",
    "thomas_opposing_level_clear",
    "thomas_breakout_data_provenance",
)

_BREAKOUT_TYPES = {
    "horizontal reversal break": "HORIZONTAL_REVERSAL",
    "horizontal reversal": "HORIZONTAL_REVERSAL",
    "horizontal continuation break": "HORIZONTAL_CONTINUATION",
    "horizontal continuation": "HORIZONTAL_CONTINUATION",
    "flag continuation": "FLAG_CONTINUATION",
    "flag breakout": "FLAG_CONTINUATION",
    "wedge breakout": "WEDGE_CONTINUATION",
    "trend line break": "TRENDLINE_BREAK",
    "trendline break": "TRENDLINE_BREAK",
    "trend line bounce": "TRENDLINE_BOUNCE",
    "trendline bounce": "TRENDLINE_BOUNCE",
    "pullback retest": "PULLBACK_RETEST",
}


def _direction(value):
    label = normalized_status(value)
    if label in {"up", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if label in {"down", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "thomas_breakout_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("thomas_breakout_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    breakout_type = _BREAKOUT_TYPES.get(normalized_status(first(state, "thomas_breakout_type")))
    direction = _direction(first(state, "thomas_breakout_direction"))
    if breakout_type is None or direction is None:
        result["thomas_breakout_assessment"] = "BREAKOUT_INPUTS_INVALID"
        result["view"] = "WAIT"
        result["reasons"] = ["the source breakout family and direction are not recognized"]
        return result
    if not volman_truth(first(state, "thomas_breakout_confirmation")):
        result["thomas_breakout_assessment"] = "BREAKOUT_UNCONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the source requires a confirmed break or retest before entry"]
        return result
    if not volman_truth(first(state, "thomas_opposing_level_clear")):
        result["thomas_breakout_assessment"] = "OPPOSING_LEVEL_BLOCKED"
        result["view"] = "WAIT"
        result["reasons"] = ["the opposing support/resistance area is not clear for this breakout direction"]
        return result
    result["thomas_breakout_assessment"] = f"CONFIRMED_{breakout_type}"
    return with_direction(result, state, direction, "the observed breakout family is confirmed and has clear opposing level geometry")
