"""Frost/Prechter impulse-wave rules as a read-only structural check."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "elliott_impulse_rules"
SOURCES = ("A.J. Frost / Robert R. Prechter — Elliott Wave Principle",)
KEYS = (
    "side",
    "elliott_impulse_direction",
    "elliott_impulse_mode",
    "elliott_impulse_subwave_count",
    "elliott_wave_2_retraces_less_than_wave_1",
    "elliott_wave_3_not_shortest",
    "elliott_wave_4_no_overlap_wave_1",
    "elliott_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_impulse_wave_annotation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "elliott_impulse_direction"))
    mode = normalized_status(first(state, "elliott_impulse_mode"))
    count = number(first(state, "elliott_impulse_subwave_count"))
    missing = [
        key for key, value in (
            ("elliott_impulse_direction", direction),
            ("elliott_impulse_mode", mode),
            ("elliott_impulse_subwave_count", count),
        ) if value is None
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not explicitly_observed(first(state, "elliott_data_provenance"), accepted=("observed", "annotated")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["elliott_data_provenance"]
        return result
    if mode not in {"motive", "impulse"} or count != 5:
        result["view"] = "WAIT"
        result["reasons"] = ["impulse rules require a five-subwave motive structure"]
        return result
    rules = (
        "elliott_wave_2_retraces_less_than_wave_1",
        "elliott_wave_3_not_shortest",
        "elliott_wave_4_no_overlap_wave_1",
    )
    if not all(volman_truth(first(state, key)) for key in rules):
        result["view"] = "WAIT"
        result["reasons"] = ["one or more non-negotiable Elliott impulse rules failed"]
        return result
    signal = "BUY" if direction in {"up", "uptrend", "bullish"} else "SELL" if direction in {"down", "downtrend", "bearish"} else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["impulse direction is not unambiguous"]
        return result
    result["elliott_impulse_assessment"] = "VALID_FIVE_WAVE_IMPULSE"
    return with_direction(result, state, signal, "observed five-wave motive structure satisfies the three impulse rules")
