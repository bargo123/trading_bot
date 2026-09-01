"""de Jong/Rindi Roll spread estimate from observed transaction prices."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "dejong_roll_spread_estimator"
SOURCES = ("Frank de Jong and Barbara Rindi — The Microstructure of Financial Markets",)
KEYS = (
    "dejong_roll_autocovariance",
    "dejong_roll_sample_n",
    "dejong_roll_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    autocovariance = number(first(state, "dejong_roll_autocovariance"))
    sample_n = number(first(state, "dejong_roll_sample_n"))
    missing = [
        key
        for key, value in (
            ("dejong_roll_autocovariance", autocovariance),
            ("dejong_roll_sample_n", sample_n),
        )
        if value is None
    ]
    if not explicitly_observed(
        first(state, "dejong_roll_data_provenance"),
        accepted=("observed", "measured", "replay"),
    ):
        missing.append("dejong_roll_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if sample_n < 3 or not sample_n.is_integer():
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["Roll estimation requires at least three observed return changes"]
        return result

    result["dejong_roll_autocovariance"] = autocovariance
    result["dejong_roll_sample_n"] = int(sample_n)
    if autocovariance < 0:
        result["dejong_roll_spread_estimate"] = 2.0 * math.sqrt(-autocovariance)
        result["dejong_roll_assessment"] = "SPREAD_ESTIMATED"
        result["reasons"] = [
            "negative lag-one transaction-price-change autocovariance supports a Roll spread estimate"
        ]
    else:
        result["dejong_roll_assessment"] = "NO_NEGATIVE_AUTOCOVARIANCE"
        result["reasons"] = [
            "Roll spread estimation requires non-positive lag-one transaction-price-change autocovariance"
        ]
    result["warnings"] = [
        "Roll is a non-directional transaction-cost diagnostic, not a BUY or SELL signal"
    ]
    return result
