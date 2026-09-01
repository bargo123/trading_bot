"""Brown's Bollinger-band touch plus confirmed signal filter."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, values, with_direction

ALGORITHM_ID = "brown_band_signal_filter"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_band_touch",
    "brown_signal_direction",
    "brown_signal_confirmed",
    "brown_signal_close_relation",
    "brown_band_data_provenance",
)


def _direction(value):
    direction = normalized_status(value).upper()
    return direction if direction in {"BUY", "SELL"} else None


def _truth(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("band_touch_and_confirmed_signal",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    touch = normalized_status(first(state, "brown_band_touch"))
    signal = _direction(first(state, "brown_signal_direction"))
    relation = normalized_status(first(state, "brown_signal_close_relation"))
    provenance = first(state, "brown_band_data_provenance")
    if not touch or signal is None or not relation or first(state, "brown_signal_confirmed") is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["band_touch_signal_confirmation_and_center_relation"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "chart")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["brown_band_data_provenance"]
        return result

    expected_touch = "lower" if signal == "BUY" else "upper"
    result["brown_band_touch"] = touch
    result["brown_signal_direction"] = signal
    if touch != expected_touch:
        result["brown_band_assessment"] = "TOUCH_DIRECTION_MISMATCH"
        result["reasons"] = ["the band touched is not the side used by the proposed reversal signal"]
        return result
    if not _truth(first(state, "brown_signal_confirmed")):
        result["brown_band_assessment"] = "UNCONFIRMED_SIGNAL"
        result["reasons"] = ["the directional signal after the band touch was not confirmed"]
        return result
    expected_relation = "below center" if signal == "BUY" else "above center"
    if relation != expected_relation:
        result["brown_band_assessment"] = "CENTER_FILTER_FAILED"
        result["reasons"] = ["the signal close is on the wrong side of the Bollinger centre-band filter"]
        return result

    result["brown_band_assessment"] = f"CONFIRMED_{touch.upper()}_BAND_{signal}"
    return with_direction(result, state, signal, "a confirmed signal followed the corresponding band touch and center-band relation")
