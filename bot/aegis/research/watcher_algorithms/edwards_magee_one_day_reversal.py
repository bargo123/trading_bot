"""Edwards--Magee One-Day Reversal, kept as a temporary exhaustion study."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "edwards_magee_one_day_reversal"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_one_day_trend",
    "em_one_day_intraday_range_pct",
    "em_one_day_net_change_pct",
    "em_one_day_volume_ratio",
    "em_one_day_reversal_confirmation",
    "em_data_provenance",
    "em_volume_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        result = base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
        return result
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "em_one_day_trend"))
    intraday_range = number(first(state, "em_one_day_intraday_range_pct"))
    net_change = number(first(state, "em_one_day_net_change_pct"))
    volume_ratio = number(first(state, "em_one_day_volume_ratio"))
    if trend not in {"up", "down"} or intraday_range is None or net_change is None or volume_ratio is None:
        result["edwards_magee_assessment"] = "INVALID_ONE_DAY_INPUT"
        result["reasons"] = ["trend and one-day range, net-change, and volume observations must be finite"]
        return result
    if not em_real_volume(state):
        result["edwards_magee_assessment"] = "SOURCE_VOLUME_UNAVAILABLE"
        result["warnings"] = ["the source requires unusually high real traded volume; tick activity is not interchangeable"]
        return result
    if intraday_range < 2.0 or volume_ratio < 1.5:
        result["edwards_magee_assessment"] = "EXHAUSTION_MAGNITUDE_INSUFFICIENT"
        result["reasons"] = ["the observed range or volume is not unusually large for a one-day reversal"]
        return result
    if abs(net_change) > 0.5:
        result["edwards_magee_assessment"] = "CLOSE_NOT_NEAR_ORIGIN"
        result["reasons"] = ["a one-day reversal should finish near its opening level after the intraday reversal"]
        return result
    if not explicitly_confirmed(first(state, "em_one_day_reversal_confirmation")):
        result["edwards_magee_assessment"] = "REVERSAL_UNCONFIRMED"
        result["reasons"] = ["the intraday push and reversal are not explicitly confirmed"]
        return result
    signal = "SELL" if trend == "up" else "BUY"
    result["edwards_magee_assessment"] = "ONE_DAY_REVERSAL"
    result["edwards_magee_horizon"] = "temporary_minor_trend"
    return with_direction(result, state, signal, "unusually wide range and volume reversed a prior one-day trend near the origin")
