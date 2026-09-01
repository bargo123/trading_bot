"""Kathy Lien's volatility-contraction medium-term breakout checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "lien_medium_term_breakout"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_environment",
    "lien_short_volatility",
    "lien_long_volatility",
    "lien_pivot_confirmation",
    "lien_moving_average_alignment",
    "lien_breakout_direction",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "lien_data_provenance")):
        missing.append("lien_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "lien_environment")) != "breakout":
        result["reasons"] = ["the medium-term breakout checklist requires a breakout environment"]
        return result
    short_volatility = number(first(state, "lien_short_volatility"))
    long_volatility = number(first(state, "lien_long_volatility"))
    if short_volatility is None or long_volatility is None or short_volatility < 0.0 or long_volatility <= 0.0:
        result["reasons"] = ["short- and long-term volatility must be positive finite observations"]
        return result
    if short_volatility >= long_volatility:
        result["reasons"] = ["short-term volatility has not contracted below long-term volatility"]
        return result
    if first(state, "lien_pivot_confirmation") is not True:
        result["reasons"] = ["pivot-point confirmation has not classified the break as a true break"]
        return result
    moving_average = normalized_status(first(state, "lien_moving_average_alignment")).upper()
    breakout = normalized_status(first(state, "lien_breakout_direction")).upper()
    if moving_average not in {"BUY", "SELL"} or breakout not in {"BUY", "SELL"} or moving_average != breakout:
        result["reasons"] = ["moving-average confluence and breakout direction are not aligned"]
        return result
    result.update(
        {
            "lien_volatility_contraction": True,
            "lien_short_to_long_volatility": short_volatility / long_volatility,
        }
    )
    return with_direction(result, state, breakout, "contracted volatility, pivot confirmation, and moving-average confluence agree")
