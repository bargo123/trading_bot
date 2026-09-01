"""Structural risk/reward and after-cost geometry algorithm."""
from __future__ import annotations
from ._common import base, first, number, side, values

ALGORITHM_ID = "risk_reward_geometry"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis", "Ernest Chan — Quantitative Trading", "Alexander Elder — The New Trading for a Living", "Robert Carver — Systematic Trading")
KEYS = ("entry", "stop", "target", "expected_net_ev", "spread_pips", "commission_usd", "slippage_usd")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("entry_stop_target",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    entry, stop, target = (number(first(state, key)) for key in ("entry", "stop", "target"))
    if not candidate_side or entry is None or stop is None or target is None:
        result["view"] = "MISSING_DATA"
        result["applicability"] = "MISSING_DATA"
        result["missing_inputs"] = ["side_and_geometry"]
        return result
    risk = entry - stop if candidate_side == "BUY" else stop - entry
    reward = target - entry if candidate_side == "BUY" else entry - target
    if risk <= 0 or reward <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["directional geometry is invalid"]
        return result
    result["risk_reward"] = reward / risk
    result["reasons"] = ["entry, structural invalidation, and target form valid geometry"]
    ev = number(first(state, "expected_net_ev"))
    if ev is not None and ev <= 0:
        result["view"] = "WAIT"
        result["warnings"] = ["recorded expected net EV is non-positive after stated costs"]
        return result
    result["view"] = candidate_side
    return result
