"""Elliott alternation guideline between impulse waves 2 and 4."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "elliott_alternation"
SOURCES = ("A.J. Frost / Robert R. Prechter — Elliott Wave Principle",)
KEYS = (
    "side",
    "elliott_alternation_wave_direction",
    "elliott_wave_2_form",
    "elliott_wave_4_form",
    "elliott_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("wave_2_wave_4_forms",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "elliott_alternation_wave_direction"))
    wave2 = normalized_status(first(state, "elliott_wave_2_form"))
    wave4 = normalized_status(first(state, "elliott_wave_4_form"))
    missing = [
        key for key, value in (
            ("elliott_alternation_wave_direction", direction),
            ("elliott_wave_2_form", wave2),
            ("elliott_wave_4_form", wave4),
        ) if not value
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not explicitly_observed(first(state, "elliott_data_provenance"), accepted=("observed", "annotated")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["elliott_data_provenance"]
        return result
    sharp = {"sharp", "zigzag"}
    sideways = {"sideways", "flat", "triangle", "double three", "triple three"}
    alternates = (wave2 in sharp and wave4 in sideways) or (wave2 in sideways and wave4 in sharp)
    if not alternates:
        result["view"] = "WAIT"
        result["reasons"] = ["wave 2 and wave 4 do not show the expected sharp/sideways alternation"]
        return result
    signal = "BUY" if direction in {"up", "uptrend", "bullish"} else "SELL" if direction in {"down", "downtrend", "bearish"} else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["alternating impulse direction is not unambiguous"]
        return result
    result["elliott_alternation_assessment"] = "ALTERNATION_PRESENT"
    return with_direction(result, state, signal, "wave 2 and wave 4 display the documented sharp/sideways alternation")
