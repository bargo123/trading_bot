"""Bob Volman's unfavorable-market/path filter for scalp setup studies."""
from __future__ import annotations

from ._common import absent, base, first, number, normalized_status, side, values, volman_missing, with_direction


ALGORITHM_ID = "volman_unfavorable_path_filter"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "side",
    "volman_market_favorable",
    "volman_path_room_pips",
    "volman_left_clustered",
    "volman_resistance_blocking",
    "volman_pressure_aligned",
)


def _explicit_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "confirmed", "observed", "clear", "aligned", "favorable"}:
        return True
    if label in {"false", "no", "unconfirmed", "blocked", "unfavorable", "clustered"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    candidate_side = side(state)
    room = number(first(state, "volman_path_room_pips"))
    observations = {
        key: _explicit_bool(first(state, key))
        for key in (
            "volman_market_favorable",
            "volman_left_clustered",
            "volman_resistance_blocking",
            "volman_pressure_aligned",
        )
    }
    if candidate_side not in {"BUY", "SELL"} or room is None or room < 0 or any(value is None for value in observations.values()):
        result["volman_path_assessment"] = "INVALID_PATH_INPUT"
        result["reasons"] = ["side, path room, and all favorable/unfavorable path observations must be explicit finite inputs"]
        return result
    if not observations["volman_market_favorable"]:
        result["volman_path_assessment"] = "UNFAVORABLE_MARKET"
        result["reasons"] = ["the source advises observing rather than applying scalp setups indiscriminately in an unfavorable market"]
        return result
    if room < 10.0:
        result["volman_path_assessment"] = "INSUFFICIENT_PATH_ROOM"
        result["reasons"] = ["the executable path does not provide the source's approximately 10-pip room to target"]
        return result
    if observations["volman_left_clustered"]:
        result["volman_path_assessment"] = "LEFT_CLUSTER_BLOCKER"
        result["reasons"] = ["clustered price action immediately left of entry can block the scalp path"]
        return result
    if observations["volman_resistance_blocking"]:
        result["volman_path_assessment"] = "VISIBLE_BLOCKER"
        result["reasons"] = ["visible chart resistance/support blocks the planned path to the scalp target"]
        return result
    if not observations["volman_pressure_aligned"]:
        result["volman_path_assessment"] = "PRESSURE_NOT_ALIGNED"
        result["reasons"] = ["the observed directional pressure does not favor the candidate"]
        return result
    result["volman_path_assessment"] = "FAVORABLE_PATH"
    result["volman_path_room_pips"] = room
    return with_direction(result, state, candidate_side, "market, directional pressure, and clear path room are observed")
