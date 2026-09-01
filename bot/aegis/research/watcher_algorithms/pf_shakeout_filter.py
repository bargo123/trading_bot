"""Jeremy du Plessis' Point-and-Figure shakeout filter.

The source describes the first countertrend signal in a newly established
trend as a possible shakeout.  It should remain a warning unless the
trendline also breaks.  This perspective is deliberately a filter/diagnostic
and does not invent a reversal from an unconfirmed shakeout.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "pf_shakeout_filter"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 146-147"
KEYS = (
    "pf_trend",
    "pf_signal",
    "pf_first_countertrend_signal",
    "pf_trendline_broken",
    "pf_data_provenance",
)


def _truthy(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not explicitly_observed(
        first(state, "pf_data_provenance"),
        accepted=("observed point and figure chart", "point and figure chart", "real point and figure"),
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_point_and_figure_chart"]
        result["reasons"] = ["shakeout analysis requires observed Point-and-Figure chart provenance"]
        return result

    trend = normalized_status(first(state, "pf_trend"))
    signal = normalized_status(first(state, "pf_signal")).upper()
    if trend not in {"up", "down"} or signal not in {"BUY", "SELL"}:
        result["view"] = "WAIT"
        result["reasons"] = ["Point-and-Figure trend and current signal must be explicit up/down and BUY/SELL observations"]
        return result

    trend_signal = "BUY" if trend == "up" else "SELL"
    if signal == trend_signal:
        result["pf_shakeout_assessment"] = "TREND_ALIGNED_SIGNAL"
        return with_direction(result, state, signal, "the observed Point-and-Figure signal follows the established trend")

    if not _truthy(first(state, "pf_first_countertrend_signal")):
        result["pf_shakeout_assessment"] = "COUNTERTREND_SIGNAL_NOT_FIRST"
        result["view"] = "WAIT"
        result["reasons"] = ["a later countertrend signal is not treated as the source's first-trend shakeout"]
        return result
    if not _truthy(first(state, "pf_trendline_broken")):
        result["pf_shakeout_assessment"] = "SHAKEOUT_IGNORE"
        result["view"] = "WAIT"
        result["reasons"] = ["the first countertrend signal is a possible shakeout and the trendline has not broken"]
        return result

    result["pf_shakeout_assessment"] = "SHAKEOUT_CONFIRMED_BREAK"
    return with_direction(
        result,
        state,
        signal,
        "the first countertrend signal is accompanied by an observed trendline break",
    )
