"""Al Brooks' discipline against converting a short-term trade into an investment."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "brooks_timeframe_discipline"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_intended_trade_type",
    "brooks_planned_horizon_s",
    "brooks_elapsed_horizon_s",
    "brooks_horizon_plan_intact",
    "brooks_timeframe_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "intact", "confirmed"}:
        return True
    if label in {"false", "no", "breached", "violated", "drifted"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "brooks_timeframe_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("brooks_timeframe_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    trade_type = normalized_status(first(state, "brooks_intended_trade_type"))
    planned = number(first(state, "brooks_planned_horizon_s"))
    elapsed = number(first(state, "brooks_elapsed_horizon_s"))
    intact = _boolean(first(state, "brooks_horizon_plan_intact"))
    if (
        trade_type not in {"scalp", "trade", "swing", "investment"}
        or planned is None
        or planned <= 0.0
        or elapsed is None
        or elapsed < 0.0
        or intact is None
    ):
        result["brooks_timeframe_assessment"] = "INVALID_TIMEFRAME_INPUTS"
        result["reasons"] = ["trade type, positive planned horizon, elapsed horizon, and plan status must be explicit"]
        return result

    exceeded = elapsed > planned
    result.update({
        "brooks_intended_trade_type": trade_type,
        "brooks_planned_horizon_s": planned,
        "brooks_elapsed_horizon_s": elapsed,
        "brooks_horizon_plan_intact": intact,
        "brooks_timeframe_exceeded": exceeded,
    })
    if not intact or exceeded:
        result["brooks_timeframe_assessment"] = "TIMEFRAME_DRIFT_EXIT_REVIEW"
        result["warnings"] = ["the source warns against holding a short-term trade as an unintended investment"]
        result["reasons"] = ["the intended trade plan was breached or its horizon was exceeded"]
    else:
        result["brooks_timeframe_assessment"] = "TIMEFRAME_PLAN_INTACT"
        result["reasons"] = ["the position remains within its declared trading timeframe"]
    return result
