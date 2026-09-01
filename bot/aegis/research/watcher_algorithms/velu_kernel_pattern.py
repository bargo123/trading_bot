"""Velu, Hardy, and Nehren's causal kernel-smoothed pattern perspective."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "velu_kernel_pattern"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_kernel_prices",
    "velu_kernel_bandwidth",
    "velu_kernel_bandwidth_selection",
    "velu_kernel_data_provenance",
)


def _prices(state):
    raw = first(state, "velu_kernel_prices")
    if not isinstance(raw, (list, tuple)):
        return None
    converted = [number(value) for value in raw]
    if len(converted) < 3 or any(value is None or value <= 0.0 for value in converted):
        return None
    return converted


def _smooth_prefix(prices, bandwidth):
    smoothed = []
    for index in range(len(prices)):
        weights = [math.exp(-0.5 * (((index - previous) / bandwidth) ** 2)) for previous in range(index + 1)]
        denominator = sum(weights)
        smoothed.append(sum(weight * prices[previous] for previous, weight in enumerate(weights)) / denominator)
    return smoothed


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_kernel_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("velu_kernel_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    prices = _prices(state)
    bandwidth = number(first(state, "velu_kernel_bandwidth"))
    selection = str(first(state, "velu_kernel_bandwidth_selection") or "").strip().lower().replace(" ", "_")
    if prices is None or bandwidth is None or bandwidth <= 0.0 or selection not in {"cross_validated", "cross_validation"}:
        result["velu_kernel_action"] = "INVALID_KERNEL_INPUT"
        result["reasons"] = ["the kernel pattern needs positive observed prices, positive bandwidth, and cross-validated bandwidth selection"]
        return result

    smoothed = _smooth_prefix(prices, bandwidth)
    previous_slope = smoothed[-2] - smoothed[-3]
    current_slope = smoothed[-1] - smoothed[-2]
    result.update(
        {
            "velu_kernel_bandwidth": bandwidth,
            "velu_kernel_bandwidth_selection": selection,
            "velu_kernel_smoothed_value": smoothed[-1],
            "velu_kernel_previous_slope": previous_slope,
            "velu_kernel_current_slope": current_slope,
        }
    )
    if previous_slope > 0.0 and current_slope < 0.0:
        return with_direction(
            {**result, "velu_kernel_action": "CONFIRMED_SMOOTHED_PEAK", "velu_kernel_extremum": "PEAK"},
            state,
            "SELL",
            "the causal kernel-smoothed slope changed from positive to negative",
        )
    if previous_slope < 0.0 and current_slope > 0.0:
        return with_direction(
            {**result, "velu_kernel_action": "CONFIRMED_SMOOTHED_TROUGH", "velu_kernel_extremum": "TROUGH"},
            state,
            "BUY",
            "the causal kernel-smoothed slope changed from negative to positive",
        )
    result["velu_kernel_action"] = "NO_SMOOTHED_EXTREMUM"
    result["reasons"] = ["the causal smoothed slope did not change sign at the current observation"]
    return result
