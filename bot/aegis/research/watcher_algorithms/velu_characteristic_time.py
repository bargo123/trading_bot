"""Velu, Hardy, and Nehren's characteristic-time normalization perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "velu_characteristic_time"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "horizon_s",
    "velu_characteristic_time_s",
    "velu_quote_event_count",
    "velu_characteristic_time_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_characteristic_time_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_characteristic_time_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    horizon = number(first(state, "horizon_s"))
    characteristic = number(first(state, "velu_characteristic_time_s"))
    event_count = number(first(state, "velu_quote_event_count"))
    if (
        horizon is None
        or characteristic is None
        or event_count is None
        or horizon <= 0
        or characteristic <= 0
        or event_count < 0
    ):
        result["velu_characteristic_time_action"] = "INVALID_TIME_SCALE_INPUT"
        result["reasons"] = [
            "characteristic-time normalization needs positive horizon/time and a nonnegative observed event count"
        ]
        return result

    normalized_time = horizon / characteristic
    result.update(
        {
            "velu_normalized_time": normalized_time,
            "velu_quote_event_count": event_count,
            "velu_event_rate_per_second": event_count / horizon,
        }
    )
    if normalized_time < 1.0:
        result["velu_characteristic_time_action"] = "UNDER_SAMPLED_CHARACTERISTIC_TIME"
        result["reasons"] = [
            "the decision horizon is shorter than one measured characteristic quote-movement time"
        ]
    else:
        result["velu_characteristic_time_action"] = "TIME_SCALE_ALIGNED"
        result["reasons"] = [
            "the decision horizon is expressed in at least one measured characteristic quote-movement time"
        ]
    return result
