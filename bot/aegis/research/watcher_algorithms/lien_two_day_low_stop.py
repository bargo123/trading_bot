"""Kathy Lien's two-day volatility stop, as a read-only risk study."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, side, values


ALGORITHM_ID = "lien_two_day_low_stop"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "side",
    "lien_two_day_entry_price",
    "lien_two_day_pip_size",
    "lien_two_day_high_history",
    "lien_two_day_low_history",
    "lien_two_day_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if len(result) >= 2 and all(item is not None and item > 0 for item in result) else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "lien_two_day_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("lien_two_day_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    candidate_side = side(state)
    entry = number(first(state, "lien_two_day_entry_price"))
    pip_size = number(first(state, "lien_two_day_pip_size"))
    highs = _series(first(state, "lien_two_day_high_history"))
    lows = _series(first(state, "lien_two_day_low_history"))
    if (
        entry is None
        or entry <= 0
        or pip_size is None
        or pip_size <= 0
        or highs is None
        or lows is None
    ):
        result["lien_two_day_stop_action"] = "INVALID_TWO_DAY_STOP_PARAMETERS"
        result["reasons"] = ["the two-day stop requires positive entry, pip, high, and low observations"]
        return result
    if candidate_side == "BUY":
        reference = min(lows[-2:])
        stop = reference - 10 * pip_size
        action = "LONG_TWO_DAY_LOW_STOP"
        valid_geometry = 0 < stop < entry
    else:
        reference = max(highs[-2:])
        stop = reference + 10 * pip_size
        action = "SHORT_TWO_DAY_HIGH_STOP"
        valid_geometry = stop > entry
    if not valid_geometry:
        result["lien_two_day_stop_action"] = "INVALID_TWO_DAY_STOP_GEOMETRY"
        result["reasons"] = ["the ten-pip offset stop is not on the protective side of the observed entry"]
        return result
    result.update(
        {
            "lien_two_day_stop_action": action,
            "lien_two_day_side": candidate_side,
            "lien_two_day_reference_price": reference,
            "lien_two_day_stop_price": stop,
            "lien_two_day_offset_pips": 10,
            "lien_two_day_stop_formula": "long: two-day low - 10 pips; short: mirrored two-day high + 10 pips",
            "directional_claim": False,
        }
    )
    return result
