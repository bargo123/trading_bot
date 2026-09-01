"""Velu/Hardy/Nehren timestamped-event duration/intensity perspective."""
from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "velu_duration_intensity"
SOURCES = ("Raja Velu, Maxence Hardy, and Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = ("velu_event_times", "velu_duration_data_provenance")


def _times(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    if len(result) < 7 or any(item is None or not math.isfinite(item) for item in result):
        return None
    return [float(item) for item in result]


def _lag_one(series: list[float]) -> float | None:
    if len(series) < 3:
        return None
    mean = statistics.fmean(series)
    denominator = statistics.fsum((item - mean) ** 2 for item in series)
    if denominator <= 0:
        return None
    numerator = statistics.fsum((series[index] - mean) * (series[index - 1] - mean) for index in range(1, len(series)))
    return numerator / denominator


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_duration_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped", "replay"),
    ):
        missing.append("velu_duration_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    timestamps = _times(first(state, "velu_event_times"))
    if timestamps is None or any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
        result["velu_duration_action"] = "INVALID_EVENT_TIMES"
        result["reasons"] = ["event timestamps must be an increasing observed sequence with enough events"]
        return result

    durations = [current - previous for previous, current in zip(timestamps, timestamps[1:])]
    split = len(durations) // 2
    prior = durations[:split]
    recent = durations[split:]
    prior_mean = statistics.fmean(prior)
    recent_mean = statistics.fmean(recent)
    lag_one = _lag_one(durations)
    result.update({
        "velu_duration_observation_n": len(durations),
        "velu_duration_mean_s": statistics.fmean(durations),
        "velu_duration_median_s": statistics.median(durations),
        "velu_duration_recent_mean_s": recent_mean,
        "velu_duration_prior_mean_s": prior_mean,
        "velu_duration_intensity_hz": 1.0 / recent_mean if recent_mean > 0 else None,
        "velu_duration_lag1_autocorrelation": lag_one,
    })
    if recent_mean < prior_mean:
        result["velu_duration_action"] = "ACTIVITY_ACCELERATION"
        result["reasons"] = ["observed event durations shortened in the recent half of the sample"]
    elif recent_mean > prior_mean:
        result["velu_duration_action"] = "ACTIVITY_DECELERATION"
        result["reasons"] = ["observed event durations lengthened in the recent half of the sample"]
    else:
        result["velu_duration_action"] = "NO_INTENSITY_CHANGE"
        result["reasons"] = ["recent and prior observed event-duration means are equal"]
    if lag_one is not None and lag_one > 0.0:
        result["warnings"] = ["positive duration dependence indicates clustered activity; it is not a directional signal"]
    return result
