"""Andrew Pole's Cuscore-style change-point guard for reversion models."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "pole_cuscore_change_point"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_cuscore",
    "pole_cuscore_threshold",
    "pole_change_direction",
    "pole_change_confirmed",
    "pole_cuscore_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_cuscore_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("pole_cuscore_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    cuscore = number(first(state, "pole_cuscore"))
    threshold = number(first(state, "pole_cuscore_threshold"))
    direction = normalized_status(first(state, "pole_change_direction"))
    if any(value is None for value in (cuscore, threshold)) or threshold <= 0:
        result["pole_change_point_action"] = "INVALID_CHANGE_POINT_INPUT"
        result["pole_reverse_candidate"] = False
        result["directional_claim"] = False
        result["reasons"] = ["Cuscore monitoring needs finite values and a positive threshold"]
        return result
    if direction not in {"up", "down"}:
        result["pole_change_point_action"] = "INVALID_CHANGE_DIRECTION"
        result["pole_reverse_candidate"] = False
        result["directional_claim"] = False
        result["reasons"] = ["change-point direction must be an explicit up or down observation"]
        return result

    result.update(
        {
            "pole_change_point_direction": direction.upper(),
            "pole_cuscore": cuscore,
            "pole_cuscore_threshold": threshold,
            "pole_reverse_candidate": False,
            "directional_claim": False,
        }
    )
    if not explicitly_confirmed(first(state, "pole_change_confirmed")):
        result["pole_change_point_action"] = "WAIT_FOR_CONFIRMATION"
        result["reasons"] = ["a Cuscore excursion is not a confirmed change point yet"]
    elif abs(cuscore) < threshold:
        result["pole_change_point_action"] = "NO_CHANGE_POINT"
        result["reasons"] = ["observed Cuscore remains below its change-point threshold"]
    else:
        result["pole_change_point_action"] = "AVOID_OR_EXIT_REVERSION"
        result["reasons"] = ["confirmed trend change invalidates an unexamined reversion assumption"]
    return result
