"""Al Brooks leg-one-equals-leg-two measured-move perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import provenance_ok

ALGORITHM_ID = "brooks_measured_move_projection"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_measured_move_leg_start",
    "brooks_measured_move_leg_end",
    "brooks_measured_move_pullback_end",
    "brooks_measured_move_direction",
    "brooks_measured_move_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    start = number(first(state, "brooks_measured_move_leg_start"))
    end = number(first(state, "brooks_measured_move_leg_end"))
    pullback = number(first(state, "brooks_measured_move_pullback_end"))
    direction = str(first(state, "brooks_measured_move_direction") or "").strip().upper()
    missing = [
        key for key, value in (
            ("brooks_measured_move_leg_start", start),
            ("brooks_measured_move_leg_end", end),
            ("brooks_measured_move_pullback_end", pullback),
            ("brooks_measured_move_direction", direction if direction in {"BUY", "SELL"} else None),
        ) if value is None
    ]
    provenance = first(state, "brooks_measured_move_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("brooks_measured_move_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    leg_size = abs(end - start)
    if leg_size <= 0 or (direction == "BUY" and end <= start) or (direction == "SELL" and end >= start):
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["the observed first leg must have non-zero movement in the declared direction"]
        return result
    target = pullback + leg_size if direction == "BUY" else pullback - leg_size
    result["analysis_stage"] = "causal_measured_move_projection"
    result["brooks_measured_move_leg_size"] = leg_size
    result["brooks_measured_move_target"] = target
    result["brooks_measured_move_assessment"] = "LEG_ONE_EQUALS_LEG_TWO_GUIDE"
    result["warnings"] = ["a measured move is a target guide and must not be treated as a guaranteed reversal or entry"]
    result["reasons"] = ["the observed pullback is paired with a same-size second-leg projection"]
    return result
