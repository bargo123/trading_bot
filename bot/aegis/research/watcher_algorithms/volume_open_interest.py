"""Murphy volume/open-interest trend-confirmation perspective.

This is a read-only futures-context study.  It deliberately does not treat
FX tick activity as traded volume or invent open interest where the venue does
not publish it.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "volume_open_interest"
SOURCES = ("John J. Murphy — Technical Analysis of the Financial Markets",)
KEYS = (
    "volume_oi_price_trend",
    "volume_oi_volume_trend",
    "volume_oi_open_interest_trend",
    "volume_oi_volume_provenance",
    "volume_oi_open_interest_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])

    if not explicitly_observed(
        first(state, "volume_oi_volume_provenance"),
        accepted=("real traded volume", "traded volume", "real volume"),
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["real_traded_volume"]
        result["reasons"] = ["volume/open-interest interpretation requires real traded-volume provenance"]
        return result
    if not explicitly_observed(
        first(state, "volume_oi_open_interest_provenance"),
        accepted=("real open interest", "open interest"),
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["real_open_interest"]
        result["reasons"] = ["open interest is not available from the supplied venue data"]
        return result

    price_trend = normalized_status(first(state, "volume_oi_price_trend"))
    volume_trend = normalized_status(first(state, "volume_oi_volume_trend"))
    open_interest_trend = normalized_status(first(state, "volume_oi_open_interest_trend"))
    if price_trend not in {"rising", "declining"} or volume_trend not in {"up", "down"} or open_interest_trend not in {"up", "down"}:
        result["view"] = "WAIT"
        result["reasons"] = ["price, volume, and open-interest trends must be explicit rising/declining observations"]
        return result

    if volume_trend == "up" and open_interest_trend == "up":
        signal = "BUY" if price_trend == "rising" else "SELL"
        result["volume_open_interest_assessment"] = "STRONG_CONTINUATION"
        return with_direction(
            result,
            state,
            signal,
            "rising volume and open interest support continuation of the observed price trend",
        )

    result["volume_open_interest_assessment"] = "TREND_END_WARNING"
    result["view"] = "WAIT"
    result["reasons"] = ["declining volume/open interest warns that the current price trend may be nearing an end"]
    return result
