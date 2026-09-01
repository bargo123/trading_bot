"""Range-breakout confirmation perspective from Schwager's chart text."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_range_breakout_confirmation"
SOURCES = ("Getting Started in Technical Analysis",)
KEYS = (
    "schwager_range_duration",
    "schwager_range_width",
    "schwager_range_narrowness",
    "schwager_breakout_direction",
    "schwager_breakout_penetration",
    "schwager_breakout_confirmation_count",
    "schwager_breakout_required_confirmation",
    "schwager_breakout_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("chart" in label or "bar" in label or "range" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_breakout_data_provenance")):
        missing.append("schwager_breakout_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    duration = number(first(state, "schwager_range_duration"))
    width = number(first(state, "schwager_range_width"))
    penetration = number(first(state, "schwager_breakout_penetration"))
    observed = number(first(state, "schwager_breakout_confirmation_count"))
    required = number(first(state, "schwager_breakout_required_confirmation"))
    direction = normalized_status(first(state, "schwager_breakout_direction")).upper()
    if (
        None in {duration, width, penetration, observed, required}
        or duration <= 0
        or width <= 0
        or penetration <= 0
        or required <= 0
        or observed < 0
        or direction not in {"UP", "DOWN"}
    ):
        result["schwager_breakout_assessment"] = "UNKNOWN"
        result["reasons"] = ["range breakout requires valid duration, width, penetration, direction, and confirmation inputs"]
        return result
    if observed < required:
        result["schwager_breakout_assessment"] = "UNCONFIRMED"
        result["reasons"] = ["the initial range penetration has not met the supplied confirmation requirement"]
        return result
    narrowness = normalized_status(first(state, "schwager_range_narrowness"))
    result["schwager_breakout_assessment"] = "CONFIRMED_NARROW" if narrowness == "narrow" else "CONFIRMED"
    signal = "BUY" if direction == "UP" else "SELL"
    return with_direction(result, state, signal, "the observed range breakout has positive penetration and the supplied confirmation count")
