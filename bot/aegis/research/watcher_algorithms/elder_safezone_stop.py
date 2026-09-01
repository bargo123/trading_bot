"""Elder's SafeZone stop calculation as a read-only noise diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "elder_safezone_stop"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = (
    "side",
    "elder_safezone_trend",
    "elder_safezone_reference_price",
    "elder_safezone_average_penetration",
    "elder_safezone_coefficient",
    "elder_safezone_lookback_days",
    "elder_safezone_penetration_count",
    "elder_safezone_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "elder_safezone_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("elder_safezone_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "elder_safezone_trend")).replace(" ", "_")
    reference = number(first(state, "elder_safezone_reference_price"))
    penetration = number(first(state, "elder_safezone_average_penetration"))
    coefficient = number(first(state, "elder_safezone_coefficient"))
    lookback = number(first(state, "elder_safezone_lookback_days"))
    count = number(first(state, "elder_safezone_penetration_count"))
    result["directional_claim"] = False
    if trend not in {"up", "down"} or any(value is None for value in (reference, penetration, coefficient, lookback, count)):
        result["elder_safezone_action"] = "INVALID_SAFEZONE_INPUT"
        result["reasons"] = ["SafeZone needs an up/down trend and finite observed noise measurements"]
        return result
    minimum_coefficient = 2.0 if trend == "up" else 3.0
    if reference <= 0 or penetration <= 0 or lookback <= 0 or count <= 0 or coefficient < minimum_coefficient:
        result["elder_safezone_action"] = "INVALID_SAFEZONE_INPUT"
        result["reasons"] = ["the observed penetration, lookback, and coefficient do not meet the source SafeZone rules"]
        return result

    buffer = penetration * coefficient
    stop_price = reference - buffer if trend == "up" else reference + buffer
    result.update({
        "elder_safezone_noise_buffer": buffer,
        "elder_safezone_stop_price": round(stop_price, 10),
        "elder_safezone_action": "LONG_NOISE_BUFFER" if trend == "up" else "SHORT_NOISE_BUFFER",
        "elder_safezone_minimum_coefficient": minimum_coefficient,
    })
    result["reasons"] = ["the stop is placed beyond the observed average counter-trend penetration"]
    return result
