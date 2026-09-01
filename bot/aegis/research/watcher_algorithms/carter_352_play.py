"""John Carter's fixed-time 3:52 late-session fade as a Watcher study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "carter_352_play"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_352_market",
    "carter_352_reference_time",
    "carter_352_entry_time",
    "carter_352_exit_time",
    "carter_352_session_timezone",
    "carter_352_reference_price",
    "carter_352_entry_price",
    "carter_352_move_direction",
    "carter_352_min_move_points",
    "carter_352_stop_points",
    "carter_352_data_provenance",
)

MARKET_RULES = {
    "ES": {"min_move": 1.0, "stop": 2.0},
    "YM": {"min_move": 10.0, "stop": 20.0},
}


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "carter_352_data_provenance"),
        accepted=("observed", "timestamped", "one minute"),
    ):
        missing.append("carter_352_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    market = normalized_status(first(state, "carter_352_market")).upper().replace("-", "")
    if market not in MARKET_RULES:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["carter_352_assessment"] = "MARKET_NOT_COVERED"
        result["reasons"] = ["the source play is defined for ES and YM futures, not this observed market"]
        return result

    timezone = normalized_status(first(state, "carter_352_session_timezone"))
    if timezone not in {"america/new york", "us/eastern", "eastern"}:
        result["carter_352_assessment"] = "SESSION_TIMEZONE_INVALID"
        result["view"] = "WAIT"
        result["reasons"] = ["the 3:52 rule is anchored to the observed US Eastern session"]
        return result
    if (
        str(first(state, "carter_352_reference_time")).strip() != "15:30"
        or str(first(state, "carter_352_entry_time")).strip() != "15:52"
        or str(first(state, "carter_352_exit_time")).strip() != "16:13"
    ):
        result["carter_352_assessment"] = "TIMING_RULE_NOT_MET"
        result["view"] = "WAIT"
        result["reasons"] = ["the source rule requires the 15:30 reference, 15:52 entry, and 16:13 exit times"]
        return result

    reference = number(first(state, "carter_352_reference_price"))
    entry = number(first(state, "carter_352_entry_price"))
    required = MARKET_RULES[market]
    supplied_min_move = number(first(state, "carter_352_min_move_points"))
    stop_points = number(first(state, "carter_352_stop_points"))
    move_direction = normalized_status(first(state, "carter_352_move_direction"))
    if (
        None in {reference, entry, supplied_min_move, stop_points}
        or reference <= 0
        or entry <= 0
        or supplied_min_move <= 0
        or stop_points <= 0
        or move_direction not in {"up", "down"}
        or supplied_min_move < required["min_move"]
        or stop_points != required["stop"]
    ):
        result["carter_352_assessment"] = "INVALID_RULE_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["the source market thresholds and observed prices must be valid"]
        return result
    actual_move = abs(entry - reference)
    expected_sign = 1 if move_direction == "up" else -1
    if (entry - reference) * expected_sign <= 0:
        result["carter_352_assessment"] = "DIRECTION_PRICE_MISMATCH"
        result["view"] = "WAIT"
        result["reasons"] = ["the observed entry price does not move in the declared 15:30 direction"]
        return result
    result["carter_352_move_points"] = actual_move
    result["carter_352_stop_points"] = stop_points
    result["carter_352_hold_minutes"] = 21
    if actual_move < supplied_min_move:
        result["carter_352_assessment"] = "MOVE_THRESHOLD_NOT_MET"
        result["view"] = "WAIT"
        result["reasons"] = ["the 15:30-to-15:52 move is smaller than the observed market threshold"]
        return result

    signal = "SELL" if move_direction == "up" else "BUY"
    result["carter_352_assessment"] = "QUALIFIED_FADE"
    return with_direction(
        result,
        state,
        signal,
        "the 15:30 move exceeded the source threshold and the 15:52 rule fades it until 16:13",
    )
