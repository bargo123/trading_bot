"""Trend-day integrity perspective from Dalton and Steidlmayer market profile work."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "dalton_trend_day_integrity"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Peter Steidlmayer — Steidlmayer on Markets",
)
KEYS = (
    "dalton_day_type",
    "dalton_direction",
    "dalton_close_location_percent",
    "dalton_countertrend_rotations",
    "dalton_directional_integrity",
    "dalton_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present"}


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "dalton_data_provenance")):
        missing.append("dalton_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    day_type = normalized_status(first(state, "dalton_day_type"))
    direction = normalized_status(first(state, "dalton_direction"))
    direction = "up" if direction in {"up", "bull", "bullish", "buy", "long"} else "down" if direction in {"down", "bear", "bearish", "sell", "short"} else None
    close_location = number(first(state, "dalton_close_location_percent"))
    rotations = number(first(state, "dalton_countertrend_rotations"))
    if day_type not in {"trend day", "trend"} or direction is None:
        result["reasons"] = ["the observed profile is not a directional trend day"]
        return result
    if close_location is None or not 0.0 <= close_location <= 10.0:
        result["reasons"] = ["trend-day confirmation requires a close within ten percent of the directional extreme"]
        return result
    if rotations is None or not 0.0 <= rotations <= 2.0:
        result["reasons"] = ["more than two countertrend rotations weaken trend-day directional integrity"]
        return result
    if not _truth(first(state, "dalton_directional_integrity")):
        result["reasons"] = ["successive profile periods do not preserve directional integrity"]
        return result
    signal = "BUY" if direction == "up" else "SELL"
    result.update(
        {
            "dalton_trend_day": True,
            "dalton_close_location_percent": close_location,
            "dalton_countertrend_rotations": rotations,
        }
    )
    return with_direction(result, state, signal, "trend-day close, limited countertrend rotation, and directional integrity agree")
