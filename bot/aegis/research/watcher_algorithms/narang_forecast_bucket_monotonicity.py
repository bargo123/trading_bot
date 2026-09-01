"""Narang's forecast-bucket monotonicity check (Inside the Black Box, ch. 9)."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "narang_forecast_bucket_monotonicity"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "narang_forecast_bucket_returns",
    "narang_forecast_bucket_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if len(result) >= 3 and all(item is not None for item in result) else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_forecast_bucket_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("narang_forecast_bucket_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    bucket_returns = _series(first(state, "narang_forecast_bucket_returns"))
    if bucket_returns is None:
        result["narang_bucket_assessment"] = "INVALID_BUCKET_RETURNS"
        result["reasons"] = ["forecast buckets must contain at least three finite ordered returns"]
        return result

    comparisons = len(bucket_returns) - 1
    monotone_pairs = sum(
        current >= previous
        for previous, current in zip(bucket_returns, bucket_returns[1:])
    )
    fraction = monotone_pairs / comparisons
    result["narang_bucket_monotonicity_fraction"] = fraction
    result["narang_bucket_count"] = len(bucket_returns)
    result["directional_claim"] = False
    if fraction == 1.0:
        result["narang_bucket_assessment"] = "MONOTONIC_FORECAST_ORDER"
        result["reasons"] = ["higher forecast buckets have non-decreasing observed returns"]
    else:
        result["narang_bucket_assessment"] = "NON_MONOTONIC_FORECAST_ORDER"
        result["reasons"] = ["forecast buckets do not have a fully ordered observed return profile"]
    return result
