"""Explicit time-stop research perspective for the read-only Watcher.

Time stops are useful for testing whether a position has made expected
progress within its declared holding window. This module only annotates a
copied state; it does not call TradeController or authorize a broker exit.
"""
from __future__ import annotations

from ._common import absent, base, first, number, values

ALGORITHM_ID = "time_stop"
SOURCES = (
    "Marcos Lopez de Prado — Advances in Financial Machine Learning",
    "Irene Aldridge — High-Frequency Trading",
    "Ernest Chan — Algorithmic Trading",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = (
    "elapsed_s",
    "horizon_s",
    "time_stop_s",
    "current_executable_pnl",
    "remaining_ev",
    "time_to_green_s",
    "never_green",
    "exit_policy",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("time_stop_evidence",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")

    elapsed = number(first(state, "elapsed_s"))
    time_stop = number(first(state, "time_stop_s"))
    if elapsed is None or time_stop is None:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["explicit_time_stop_rule"]
        result["reasons"] = ["Watcher will not infer a time stop from horizon or elapsed time"]
        return result
    if elapsed < 0 or time_stop < 0:
        result["time_stop_assessment"] = "UNKNOWN"
        result["reasons"] = ["elapsed time and time-stop values must be finite and non-negative"]
        return result

    current_pnl = number(first(state, "current_executable_pnl"))
    remaining_ev = number(first(state, "remaining_ev"))
    time_to_green = number(first(state, "time_to_green_s"))
    never_green = first(state, "never_green")
    no_progress = (
        never_green is True
        or (current_pnl is not None and current_pnl <= 0 and (remaining_ev is None or remaining_ev <= 0))
    )

    if elapsed < time_stop:
        result["management_action"] = "CONTINUE_WINDOW"
        result["time_stop_assessment"] = "WITHIN_WINDOW"
        result["reasons"] = ["the explicit research time-stop window has not elapsed"]
        return result

    if no_progress:
        result["management_action"] = "TIME_STOP_CANDIDATE"
        result["time_stop_assessment"] = "ELAPSED_WITHOUT_PROGRESS"
        result["reasons"] = [
            "explicit research time-stop elapsed without evidence that continuation is better",
        ]
        return result

    if (
        (current_pnl is not None and current_pnl > 0)
        or (remaining_ev is not None and remaining_ev > 0)
        or (time_to_green is not None and time_to_green >= 0)
    ):
        result["management_action"] = "REASSESS_PROFIT"
        result["time_stop_assessment"] = "PROGRESS_PRESENT"
        result["reasons"] = ["the explicit time-stop elapsed but progress evidence is present"]
        return result

    result["management_action"] = "REASSESS_PROGRESS"
    result["time_stop_assessment"] = "INSUFFICIENT_PROGRESS_EVIDENCE"
    result["reasons"] = ["time-stop elapsed but the copied state does not establish progress or failure"]
    return result
