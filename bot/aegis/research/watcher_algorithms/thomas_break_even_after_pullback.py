"""The 10XROI system's delayed break-even protection study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "thomas_break_even_after_pullback"
SOURCES = ("LR Thomas — The 10XROI Trading System",)
KEYS = (
    "thomas_trade_in_profit",
    "thomas_first_hourly_pullback_complete",
    "thomas_continued_after_first_pullback",
    "thomas_break_even_ready",
    "thomas_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "thomas_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("thomas_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    if not _truthy(first(state, "thomas_trade_in_profit")):
        result["thomas_breakeven_assessment"] = "NOT_IN_PROFIT"
        result["reasons"] = ["break-even protection is studied only after a trade has moved in its favor"]
        return result
    if not _truthy(first(state, "thomas_first_hourly_pullback_complete")):
        result["thomas_breakeven_assessment"] = "WAIT_FOR_FIRST_PULLBACK"
        result["reasons"] = ["the source deliberately waits for the first hourly pullback before moving the stop"]
        return result
    if not _truthy(first(state, "thomas_continued_after_first_pullback")):
        result["thomas_breakeven_assessment"] = "CONTINUATION_NOT_CONFIRMED"
        result["reasons"] = ["the move has not continued after the first pullback"]
        return result
    if not _truthy(first(state, "thomas_break_even_ready")):
        result["thomas_breakeven_assessment"] = "PROTECTION_NOT_READY"
        result["reasons"] = ["the supplied management state does not authorize a break-even move"]
        return result
    result["thomas_breakeven_assessment"] = "MOVE_TO_BREAK_EVEN"
    result["thomas_management_action"] = "MOVE_STOP_TO_BREAK_EVEN"
    result["reasons"] = ["the source's first-pullback-and-continuation condition is complete"]
    return result
