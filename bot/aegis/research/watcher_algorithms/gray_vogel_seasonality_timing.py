"""Gray--Vogel momentum-seasonality timing perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, values

ALGORITHM_ID = "gray_vogel_seasonality_timing"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_seasonal_month",
    "gray_seasonal_sample_n",
    "gray_seasonal_expectancy",
    "gray_seasonal_validation",
    "gray_seasonal_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "gray_seasonal_data_provenance"),
        accepted=("observed", "measured", "historical"),
    ):
        missing.append("gray_seasonal_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    month = number(first(state, "gray_seasonal_month"))
    sample = number(first(state, "gray_seasonal_sample_n"))
    expectancy = number(first(state, "gray_seasonal_expectancy"))
    result["directional_claim"] = False
    if (
        month is None
        or sample is None
        or expectancy is None
        or not month.is_integer()
        or not 1 <= month <= 12
        or sample <= 0
    ):
        result["gray_seasonal_assessment"] = "INVALID_SEASONAL_INPUT"
        result["reasons"] = ["seasonality timing needs a valid calendar month and a positive observed sample"]
        return result
    if not explicitly_validated(
        first(state, "gray_seasonal_validation"),
        accepted=("validated", "walk forward", "sealed oos"),
    ) or expectancy <= 0:
        result["gray_seasonal_assessment"] = "SEASONAL_EDGE_NOT_IDENTIFIED"
        result["reasons"] = ["the seasonal estimate is not positive and validated out of sample"]
        return result

    result.update({"gray_seasonal_month": int(month), "gray_seasonal_expectancy": expectancy})
    if int(month) in {2, 5, 8, 11}:
        result["gray_seasonal_assessment"] = "PRE_QUARTER_END_MOMENTUM_WINDOW"
        result["reasons"] = ["the validated positive seasonal estimate falls in the source's pre-quarter-end rebalance window"]
    else:
        result["gray_seasonal_assessment"] = "SEASONAL_EDGE_NOT_IDENTIFIED"
        result["reasons"] = ["the validated estimate does not identify the source's pre-quarter-end momentum timing window"]
    return result
