"""Davey's Euro Night limit-bracket strategy, as a read-only bar replay."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values, with_direction


ALGORITHM_ID = "davey_euro_night_strategy"
SOURCES = ("Kevin J. Davey — Building Winning Algorithmic Trading Systems",)
KEYS = (
    "davey_night_time_hhmm",
    "davey_night_position_flat",
    "davey_night_nb",
    "davey_night_natr",
    "davey_night_atr_multiplier",
    "davey_night_tr_multiplier",
    "davey_night_stop_loss",
    "davey_night_current_price",
    "davey_night_high_history",
    "davey_night_low_history",
    "davey_night_true_range_history",
    "davey_night_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if result and all(item is not None for item in result) else None


def _truth(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "flat", "observed", "valid"}


def _valid_hhmm(value):
    parsed = number(value)
    if parsed is None or parsed != int(parsed):
        return None
    parsed = int(parsed)
    return parsed if 0 <= parsed <= 2359 and parsed % 100 < 60 else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "davey_night_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("davey_night_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    time_hhmm = _valid_hhmm(first(state, "davey_night_time_hhmm"))
    nb = number(first(state, "davey_night_nb"))
    natr = number(first(state, "davey_night_natr"))
    atr_multiplier = number(first(state, "davey_night_atr_multiplier"))
    tr_multiplier = number(first(state, "davey_night_tr_multiplier"))
    stop_loss = number(first(state, "davey_night_stop_loss"))
    current = number(first(state, "davey_night_current_price"))
    highs = _series(first(state, "davey_night_high_history"))
    lows = _series(first(state, "davey_night_low_history"))
    true_ranges = _series(first(state, "davey_night_true_range_history"))
    integer_params = lambda value: value is not None and value > 0 and value == int(value)
    if (
        time_hhmm is None
        or not _truth(first(state, "davey_night_position_flat"))
        or not integer_params(nb)
        or not integer_params(natr)
        or atr_multiplier is None
        or atr_multiplier <= 0
        or tr_multiplier is None
        or tr_multiplier <= 0
        or stop_loss is None
        or stop_loss <= 0
        or current is None
        or highs is None
        or lows is None
        or true_ranges is None
        or len(highs) < int(nb)
        or len(lows) < int(nb)
        or len(true_ranges) < int(natr)
    ):
        result["davey_night_action"] = "INVALID_NIGHT_PARAMETERS"
        result["reasons"] = ["the Euro Night replay requires valid flat-state, session, ATR, and bar-history inputs"]
        return result
    if not 1800 <= time_hhmm <= 2359:
        result["davey_night_action"] = "OUTSIDE_NIGHT_SESSION"
        result["reasons"] = ["the source strategy only places entries from 18:00 through 23:59"]
        return result

    nb = int(nb)
    natr = int(natr)
    atr = sum(true_ranges[-natr:]) / natr
    true_range = true_ranges[-1]
    if atr <= 0 or true_range <= 0 or any(high < low for high, low in zip(highs[-nb:], lows[-nb:])):
        result["davey_night_action"] = "INVALID_NIGHT_GEOMETRY"
        result["reasons"] = ["the source limit prices require positive range and valid high/low geometry"]
        return result

    long_price = sum(highs[-nb:]) / nb - atr_multiplier * atr
    short_price = sum(lows[-nb:]) / nb + atr_multiplier * atr
    if long_price <= 0 or short_price <= 0:
        result["davey_night_action"] = "INVALID_NIGHT_ENTRY_PRICE"
        result["reasons"] = ["the calculated limit entry price is not positive"]
        return result
    selected_side = "BUY" if abs(current - long_price) <= abs(current - short_price) else "SELL"
    entry = long_price if selected_side == "BUY" else short_price
    target = entry + tr_multiplier * true_range if selected_side == "BUY" else entry - tr_multiplier * true_range
    if target <= 0:
        result["davey_night_action"] = "INVALID_NIGHT_TARGET"
        result["reasons"] = ["the calculated source target is not positive"]
        return result

    result.update(
        {
            "davey_night_action": "PLACE_LONG_LIMIT" if selected_side == "BUY" else "PLACE_SHORT_LIMIT",
            "davey_night_selected_side": selected_side,
            "davey_night_entry_price": entry,
            "davey_night_long_entry_price": long_price,
            "davey_night_short_entry_price": short_price,
            "davey_night_target_price": target,
            "davey_night_stop_loss": stop_loss,
            "davey_night_atr": atr,
            "davey_night_true_range": true_range,
            "directional_claim": True,
        }
    )
    return with_direction(result, state, selected_side, "source Euro Night limit bracket selected the entry closest to price")
