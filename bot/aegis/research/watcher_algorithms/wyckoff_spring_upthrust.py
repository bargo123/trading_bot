"""Wyckoff spring/upthrust event perspective with explicit confirmation."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, strings, values, with_direction

ALGORITHM_ID = "wyckoff_spring_upthrust"
SOURCES = (
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Anna Coulling — A Complete Guide to Volume Price Analysis",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = ("wyckoff_event", "wyckoff_confirmation", "wyckoff_volume_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_wyckoff_event",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    event = strings(state, "wyckoff_event")
    price_confirmed = explicitly_confirmed(first(state, "wyckoff_confirmation"))
    volume_confirmation = strings(state, "wyckoff_volume_confirmation")
    volume_confirmed = explicitly_confirmed(first(state, "wyckoff_volume_confirmation"))
    if not price_confirmed or not volume_confirmed:
        result["view"] = "WAIT"
        result["reasons"] = ["spring or upthrust requires separate explicit price and volume confirmation"]
        return result
    if "proxy" in volume_confirmation:
        result["warnings"] = ["volume confirmation is a declared quote/tick proxy"]
        result["view"] = "WAIT"
        result["reasons"] = ["Wyckoff volume confirmation is not a real traded-volume observation"]
        return result
    if "spring" in event:
        return with_direction(result, state, "BUY", "confirmed Wyckoff spring supports a test of upward reversal")
    if "upthrust" in event:
        return with_direction(result, state, "SELL", "confirmed Wyckoff upthrust supports a test of downward reversal")
    result["view"] = "WAIT"
    result["reasons"] = ["recorded Wyckoff event is not a supported spring or upthrust"]
    return result
