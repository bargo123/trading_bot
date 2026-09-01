"""Chan's short-horizon momentum after a confirmed stop-level breach."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "chan_stop_order_momentum"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_stop_level",
    "chan_stop_price",
    "chan_stop_level_role",
    "chan_stop_break_confirmed",
    "chan_stop_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "chan_stop_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("chan_stop_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    level = number(first(state, "chan_stop_level"))
    price = number(first(state, "chan_stop_price"))
    role = normalized_status(first(state, "chan_stop_level_role"))
    if level is None or price is None or level <= 0 or price <= 0 or role not in {"support", "resistance"}:
        result["chan_stop_assessment"] = "INVALID_STOP_LEVEL"
        result["view"] = "WAIT"
        result["reasons"] = ["stop level, executable price, and level role must be valid observations"]
        return result
    if not volman_truth(first(state, "chan_stop_break_confirmed")):
        result["chan_stop_assessment"] = "BREACH_UNCONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["stop-trigger momentum requires a confirmed breach of support or resistance"]
        return result
    if role == "resistance" and price > level:
        result["chan_stop_assessment"] = "RESISTANCE_STOP_CASCADE"
        return with_direction(result, state, "BUY", "a confirmed resistance breach can trigger buy stops and short-horizon continuation")
    if role == "support" and price < level:
        result["chan_stop_assessment"] = "SUPPORT_STOP_CASCADE"
        return with_direction(result, state, "SELL", "a confirmed support breach can trigger sell stops and short-horizon continuation")
    result["chan_stop_assessment"] = "NO_BREACH"
    result["view"] = "WAIT"
    result["reasons"] = ["the observed price has not breached the declared stop level"]
    return result
