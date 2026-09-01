"""Velu, Hardy, and Nehren's weighted moving-average band rule."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "velu_bwma_bollinger_rule"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_bwma_prices",
    "velu_bwma_band_multiplier",
    "velu_bwma_data_provenance",
)


def _prices(state):
    raw = first(state, "velu_bwma_prices")
    if not isinstance(raw, (list, tuple)):
        return None
    converted = [number(value) for value in raw]
    if len(converted) < 2 or any(value is None or value <= 0.0 for value in converted):
        return None
    return converted


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_bwma_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("velu_bwma_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    prices = _prices(state)
    multiplier = number(first(state, "velu_bwma_band_multiplier"))
    if candidate_side is None or prices is None or multiplier is None or multiplier <= 0.0:
        result["velu_bwma_action"] = "INVALID_BWMA_INPUT"
        result["reasons"] = ["the weighted band rule needs positive observed prices and a positive band multiplier"]
        return result

    # The book's BWMA weights older-to-newer observations 1..n.  The sample
    # standard deviation is measured around that weighted center; all inputs
    # are observations available at this decision point.
    weights = list(range(1, len(prices) + 1))
    bwma = sum(weight * price for weight, price in zip(weights, prices, strict=True)) / sum(weights)
    sample_variance = sum((price - bwma) ** 2 for price in prices) / (len(prices) - 1)
    deviation = math.sqrt(sample_variance)
    upper = bwma + multiplier * deviation
    lower = bwma - multiplier * deviation
    current = prices[-1]
    result.update(
        {
            "velu_bwma_value": bwma,
            "velu_bwma_current_price": current,
            "velu_bwma_sample_std": deviation,
            "velu_bwma_upper_band": upper,
            "velu_bwma_lower_band": lower,
            "velu_bwma_band_multiplier": multiplier,
        }
    )
    if current > upper:
        return with_direction(
            {**result, "velu_bwma_action": "UPPER_BAND_SELL"},
            state,
            "SELL",
            "the observed price is above the weighted moving-average upper band",
        )
    if current < lower:
        return with_direction(
            {**result, "velu_bwma_action": "LOWER_BAND_BUY"},
            state,
            "BUY",
            "the observed price is below the weighted moving-average lower band",
        )
    result["velu_bwma_action"] = "INSIDE_BANDS"
    result["reasons"] = ["the observed price remains inside the weighted moving-average bands"]
    return result
