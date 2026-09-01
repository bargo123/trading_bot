"""Schwager's narrow-consolidation-at-range-edge observation."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction


ALGORITHM_ID = "schwager_narrow_consolidation_bias"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_consolidation_location",
    "schwager_consolidation_narrow",
    "schwager_broader_range_context",
    "schwager_consolidation_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "schwager_consolidation_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("schwager_consolidation_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    location = normalized_status(first(state, "schwager_consolidation_location"))
    if location not in {"upper", "upper end", "lower", "lower end"}:
        result["schwager_consolidation_assessment"] = "LOCATION_UNRECOGNIZED"
        result["view"] = "WAIT"
        result["reasons"] = ["the consolidation must be located at the upper or lower end of a broader range"]
        return result
    if not volman_truth(first(state, "schwager_broader_range_context")):
        result["schwager_consolidation_assessment"] = "BROADER_RANGE_UNCONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the broader trading-range context has not been observed"]
        return result
    if not volman_truth(first(state, "schwager_consolidation_narrow")):
        result["schwager_consolidation_assessment"] = "CONSOLIDATION_NOT_NARROW"
        result["view"] = "WAIT"
        result["reasons"] = ["the source observation applies to a narrow consolidation"]
        return result

    upper = location in {"upper", "upper end"}
    signal = "BUY" if upper else "SELL"
    result["schwager_consolidation_assessment"] = "UPPER_NARROW_BULLISH" if upper else "LOWER_NARROW_BEARISH"
    return with_direction(result, state, signal, "narrow consolidation at the corresponding range edge supplies the source directional bias")
