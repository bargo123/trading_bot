"""W. D. Gann's observed 50-percent, or half-way, point interaction."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "gann_halfway_point"
SOURCES = ("W. D. Gann — How to Make Profits in Commodities",)
SOURCE_PAGES = "pp. 25-31"
KEYS = (
    "gann_halfway_percent",
    "gann_halfway_move",
    "gann_halfway_interaction",
    "gann_halfway_confirmed",
    "gann_halfway_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "gann_halfway_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("gann_halfway_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    percent = number(first(state, "gann_halfway_percent"))
    if percent is None or abs(percent - 50.0) > 0.5:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed interaction is not at the source's 50-percent half-way point"]
        return result
    if not volman_truth(first(state, "gann_halfway_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the half-way-point interaction is not confirmed"]
        return result

    move = normalized_status(first(state, "gann_halfway_move"))
    interaction = normalized_status(first(state, "gann_halfway_interaction"))
    buy_interactions = {"held support", "support held", "crossed up", "crossed above"}
    sell_interactions = {"held resistance", "resistance held", "crossed down", "crossed below"}
    if move == "up" and interaction in buy_interactions:
        result["gann_halfway_assessment"] = "BULLISH_50_PERCENT_INTERACTION"
        return with_direction(result, state, "BUY", "the up move held or crossed above the observed 50-percent point")
    if move == "down" and interaction in sell_interactions:
        result["gann_halfway_assessment"] = "BEARISH_50_PERCENT_INTERACTION"
        return with_direction(result, state, "SELL", "the down move held or crossed below the observed 50-percent point")

    result["view"] = "WAIT"
    result["reasons"] = ["the half-way interaction has no confirmed direction or contradicts the move"]
    return result
