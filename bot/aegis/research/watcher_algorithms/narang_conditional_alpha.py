"""Narang's secondary-conditioner rule: require signal agreement."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, values, with_direction

ALGORITHM_ID = "narang_conditional_alpha"
SOURCES = ("Rishi K Narang — Inside the Black Box",)
KEYS = (
    "narang_primary_signal",
    "narang_conditioning_signal",
    "narang_primary_direction",
    "narang_conditioning_direction",
    "narang_conditioning_confirmed",
    "narang_alpha_data_provenance",
)


def _direction(value):
    normalized = normalized_status(value).upper()
    return normalized if normalized in {"BUY", "SELL"} else None


def _confirmed(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("primary_and_conditioning_signals",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    primary = _direction(first(state, "narang_primary_direction"))
    conditioning = _direction(first(state, "narang_conditioning_direction"))
    provenance = first(state, "narang_alpha_data_provenance")
    missing = [
        key
        for key, value in (
            ("narang_primary_signal", first(state, "narang_primary_signal")),
            ("narang_conditioning_signal", first(state, "narang_conditioning_signal")),
            ("narang_primary_direction", primary),
            ("narang_conditioning_direction", conditioning),
            ("narang_conditioning_confirmed", first(state, "narang_conditioning_confirmed")),
        )
        if value is None or value == ""
    ]
    if missing or not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
            missing.append("narang_alpha_data_provenance")
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = list(dict.fromkeys(missing))
        return result

    result["narang_primary_direction"] = primary
    result["narang_conditioning_direction"] = conditioning
    result["directional_claim"] = True
    if primary != conditioning:
        result["narang_conditional_assessment"] = "DIRECTION_DISAGREEMENT"
        result["reasons"] = ["the conditioning signal does not confirm the primary alpha direction"]
        return result
    if not _confirmed(first(state, "narang_conditioning_confirmed")):
        result["narang_conditional_assessment"] = "UNCONFIRMED"
        result["reasons"] = ["the secondary conditioning signal is present but not confirmed"]
        return result

    result["narang_conditional_assessment"] = "CONFIRMED_AGREEMENT"
    return with_direction(
        result,
        state,
        primary,
        "the primary alpha is activated only when the conditioning signal agrees",
    )
