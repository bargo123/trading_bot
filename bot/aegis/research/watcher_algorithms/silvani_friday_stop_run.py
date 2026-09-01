"""Silvani's Friday artificial-support stop-run fade perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "silvani_friday_stop_run"
SOURCES = ("Beat the Forex Dealer",)
KEYS = (
    "silvani_friday_event",
    "silvani_weekday",
    "silvani_retail_side",
    "silvani_artificial_support",
    "silvani_stop_cluster_observed",
    "silvani_price_approaching_support",
    "silvani_support_level",
    "silvani_current_price",
    "silvani_pip_size",
    "silvani_target_pips",
    "silvani_friday_data_provenance",
)


def _truth(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed"}


def evaluate(state):
    found = values(state, *KEYS)
    support = number(first(state, "silvani_support_level"))
    current = number(first(state, "silvani_current_price"))
    pip = number(first(state, "silvani_pip_size"))
    target = number(first(state, "silvani_target_pips"))
    missing = [
        key
        for key, value in (
            ("silvani_friday_event", first(state, "silvani_friday_event")),
            ("silvani_weekday", first(state, "silvani_weekday")),
            ("silvani_retail_side", first(state, "silvani_retail_side")),
            ("silvani_artificial_support", first(state, "silvani_artificial_support")),
            ("silvani_stop_cluster_observed", first(state, "silvani_stop_cluster_observed")),
            ("silvani_price_approaching_support", first(state, "silvani_price_approaching_support")),
            ("silvani_support_level", support),
            ("silvani_current_price", current),
            ("silvani_pip_size", pip),
            ("silvani_target_pips", target),
        )
        if value is None or value == ""
    ]
    provenance = first(state, "silvani_friday_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "study")):
        missing.append("silvani_friday_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "side")) != "sell":
        result["reasons"] = ["the documented setup fades retail buying near artificial support"]
        return result
    if normalized_status(first(state, "silvani_friday_event")) != "friday stop run setup" or normalized_status(first(state, "silvani_weekday")) != "friday":
        result["reasons"] = ["the source stop-run example requires a Friday setup"]
        return result
    if normalized_status(first(state, "silvani_retail_side")) != "buy":
        result["reasons"] = ["retail buying is not the observed side being faded"]
        return result
    if not _truth(first(state, "silvani_artificial_support")) or not _truth(first(state, "silvani_stop_cluster_observed")) or not _truth(first(state, "silvani_price_approaching_support")):
        result["reasons"] = ["artificial support, a stop cluster, and approach evidence are all required"]
        return result
    if any(value is None or value <= 0 for value in (support, current, pip, target)) or current < support:
        result["reasons"] = ["support, current price, pip size, and target must form a valid above-support geometry"]
        return result
    distance = (current - support) / pip
    if distance > 2.0 + 1e-9:
        result["reasons"] = ["price is not close enough to the support stop cluster for the documented fade"]
        return result
    if not 10.0 <= target <= 20.0:
        result["reasons"] = ["the documented quick stop-run objective is 10 to 20 pips"]
        return result
    result["silvani_stop_run_assessment"] = "FADE_RETAIL_SUPPORT"
    result["silvani_distance_to_support_pips"] = distance
    return with_direction(result, state, "SELL", "the observed Friday stop-run setup fades retail support buying")
