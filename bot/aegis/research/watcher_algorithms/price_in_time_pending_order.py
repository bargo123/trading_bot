"""Price-in-Time second-pending-order management perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, side, values, volman_truth

ALGORITHM_ID = "price_in_time_pending_order"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "side",
    "pit_first_trade_status",
    "pit_second_pending_order_active",
    "pit_second_pending_order_side",
    "pit_pending_order_data_provenance",
    "pit_session_window",
    "pit_direction_change_after_target",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("first_trade_and_second_pending_state",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    status = normalized_status(first(state, "pit_first_trade_status"))
    pending_side = str(first(state, "pit_second_pending_order_side") or "").strip().upper()
    if candidate_side is None or not status or pending_side not in {"BUY", "SELL"}:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["side_trade_status_and_pending_side"]
        return result
    if not first(state, "pit_pending_order_data_provenance") or any(token in normalized_status(first(state, "pit_pending_order_data_provenance")) for token in ("synthetic", "fixture", "unknown", "unavailable")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["pit_pending_order_data_provenance"]
        return result
    if pending_side == candidate_side:
        result["view"] = "WAIT"
        result["reasons"] = ["the second pending order must be on the opposite NTZ side"]
        return result
    active = volman_truth(first(state, "pit_second_pending_order_active"))
    session_window = normalized_status(first(state, "pit_session_window"))
    direction_change = volman_truth(first(state, "pit_direction_change_after_target"))
    if status in {"target reached", "profit target"}:
        result["pit_pending_order_action"] = "CANCEL_SECOND_PENDING"
        result["view"] = "WAIT"
        result["reasons"] = ["the source cancels the opposite pending order after the first trade reaches target"]
        return result
    if status in {"tp1 reached", "tp2 reached"}:
        if direction_change and session_window in {"london morning", "london new york overlap"} and active:
            result["pit_pending_order_action"] = "KEEP_OPPOSITE_PENDING"
            result["view"] = "WAIT"
            result["reasons"] = ["after an early target and observed reversal, the source retains the opposite order during the active session window"]
            return result
        result["pit_pending_order_action"] = "CANCEL_SECOND_PENDING"
        result["view"] = "WAIT"
        result["reasons"] = ["the opposite order is not retained after the target outside the source's early-session reversal window"]
        return result
    if status in {"both stop loss", "two stop losses", "day stopped"}:
        result["pit_pending_order_action"] = "DAY_COMPLETE"
        result["view"] = "WAIT"
        result["reasons"] = ["both allowed trades stopped; no further same-day NTZ order is retained"]
        return result
    if status in {"stop loss", "stopped", "first stop loss"} and active and session_window not in {"post london", "outside source window"}:
        result["pit_pending_order_action"] = "KEEP_OPPOSITE_PENDING"
        result["view"] = "WAIT"
        result["reasons"] = ["after the first stop the source permits only the opposite pending order"]
        return result
    result["pit_pending_order_action"] = "NO_ACTION"
    result["view"] = "WAIT"
    result["reasons"] = ["pending-order state does not match a source-defined target or stop event"]
    return result
