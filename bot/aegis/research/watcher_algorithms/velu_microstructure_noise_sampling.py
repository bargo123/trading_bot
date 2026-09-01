"""Velu/Hardy/Nehren diagnostic for sampling frequency and microstructure noise."""
from __future__ import annotations

import math
import statistics
from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "velu_microstructure_noise_sampling"
SOURCES = ("Raja Velu, Maxence Hardy, and Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "velu_sampling_fast_returns",
    "velu_sampling_slow_returns",
    "velu_sampling_fast_interval_s",
    "velu_sampling_slow_interval_s",
    "velu_sampling_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if result and all(item is not None and math.isfinite(item) for item in result) else None


def _lag_one_autocorrelation(series: list[float]) -> float | None:
    if len(series) < 3:
        return None
    mean = statistics.fmean(series)
    variance = statistics.fsum((item - mean) ** 2 for item in series)
    if variance <= 0:
        return None
    covariance = statistics.fsum((series[index] - mean) * (series[index - 1] - mean) for index in range(1, len(series)))
    return covariance / variance


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_sampling_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped", "replay"),
    ):
        missing.append("velu_sampling_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    fast = _series(first(state, "velu_sampling_fast_returns"))
    slow = _series(first(state, "velu_sampling_slow_returns"))
    fast_interval = number(first(state, "velu_sampling_fast_interval_s"))
    slow_interval = number(first(state, "velu_sampling_slow_interval_s"))
    if (
        fast is None
        or slow is None
        or len(fast) < 3
        or len(slow) < 2
        or fast_interval is None
        or fast_interval <= 0
        or slow_interval is None
        or slow_interval <= 0
        or fast_interval >= slow_interval
    ):
        result["velu_sampling_action"] = "INVALID_SAMPLING_INPUTS"
        result["reasons"] = ["fast and slow return samples need valid distinct intervals and enough observations"]
        return result

    fast_variance = statistics.pvariance(fast)
    slow_variance = statistics.pvariance(slow)
    lag_one = _lag_one_autocorrelation(fast)
    result.update({
        "velu_sampling_fast_interval_s": fast_interval,
        "velu_sampling_slow_interval_s": slow_interval,
        "velu_sampling_fast_observation_n": len(fast),
        "velu_sampling_slow_observation_n": len(slow),
        "velu_sampling_fast_variance": fast_variance,
        "velu_sampling_slow_variance": slow_variance,
        "velu_sampling_fast_lag1_autocorrelation": lag_one,
        "velu_sampling_variance_gap": max(0.0, fast_variance - slow_variance),
    })
    if lag_one is not None and lag_one < 0.0:
        result["velu_sampling_action"] = "MICROSTRUCTURE_NOISE_REVIEW"
        result["warnings"] = [
            "negative fine-interval return autocorrelation is consistent with bid/ask bounce or other microstructure noise; use a finite sampling interval"
        ]
        result["reasons"] = ["the fast sample shows negative lag-1 dependence relative to the slower sample"]
    else:
        result["velu_sampling_action"] = "NO_NEGATIVE_LAG1_WARNING"
        result["reasons"] = ["the observed fast sample does not show negative lag-1 dependence"]
    return result
