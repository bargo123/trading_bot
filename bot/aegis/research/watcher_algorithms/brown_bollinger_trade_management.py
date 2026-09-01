"""Brown's Bollinger centre/outer-band open-trade management perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "brown_bollinger_trade_management"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_trade_side",
    "brown_entry_center_relation",
    "brown_current_center_relation",
    "brown_trade_profit_positive",
    "brown_management_action_viable",
    "brown_opposite_band_touched",
    "brown_bollinger_management_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "bollinger" in label and "trade" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_bollinger_management_data_provenance")):
        missing.append("brown_bollinger_management_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    trade_side = normalized_status(first(state, "brown_trade_side"))
    entry = normalized_status(first(state, "brown_entry_center_relation"))
    current = normalized_status(first(state, "brown_current_center_relation"))
    if trade_side not in {"buy", "sell"} or entry not in {"below center", "above center"} or current not in {"below center", "above center"}:
        result["brown_management_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["trade side and centre-band relationships must be explicit"]
        return result
    if not _truth(first(state, "brown_trade_profit_positive")):
        result["brown_management_assessment"] = "NO_PROFIT_TO_PROTECT"
        result["reasons"] = ["the source's partial-close/protection action requires a profitable position"]
        return result
    if not _truth(first(state, "brown_management_action_viable")):
        result["brown_management_assessment"] = "ACTION_NOT_VIABLE"
        result["reasons"] = ["the observed profit or stop geometry does not make the discretionary management action viable"]
        return result
    if _truth(first(state, "brown_opposite_band_touched")):
        result["brown_management_assessment"] = "OPPOSITE_BAND_ACTION"
        result["management_action"] = "CONSIDER_PARTIAL_CLOSE_OR_PROTECTIVE_STOP"
        result["reasons"] = ["price reached the opposite Bollinger band, a source-described place to consider action"]
        return result
    crossed = (trade_side == "buy" and entry == "below center" and current == "above center") or (trade_side == "sell" and entry == "above center" and current == "below center")
    if crossed:
        result["brown_management_assessment"] = "CENTER_CROSS_PARTIAL_AND_PROTECT"
        result["management_action"] = "CONSIDER_PARTIAL_CLOSE_AND_MOVE_STOP_TO_BREAK_EVEN"
        result["reasons"] = ["price crossed the centre band in the profitable direction after the source-style entry relation"]
        return result
    result["brown_management_assessment"] = "NO_MANAGEMENT_TRIGGER"
    result["reasons"] = ["no source-described centre-cross or opposite-band management event is observed"]
    return result
