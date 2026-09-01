"""Kathy Lien's seven-day extension turn, as a read-only daily replay."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "lien_high_probability_turn"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_turn_timeframe",
    "lien_turn_entry_time_ny",
    "lien_turn_entry_price",
    "lien_turn_pip_size",
    "lien_turn_daily_bars",
    "lien_turn_data_provenance",
)


def _valid_hhmm(value):
    if isinstance(value, str) and ":" in value:
        hours, minutes = value.strip().split(":", 1)
        if not hours.isdigit() or not minutes.isdigit():
            return None
        parsed = int(hours) * 100 + int(minutes)
    else:
        numeric = number(value)
        if numeric is None or numeric != int(numeric):
            return None
        parsed = int(numeric)
    return parsed if 0 <= parsed <= 2359 and parsed % 100 < 60 else None


def _daily_bars(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    bars = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        opening = number(item.get("open"))
        closing = number(item.get("close"))
        if opening is None or closing is None or opening <= 0 or closing <= 0:
            return None
        bars.append((opening, closing))
    return bars if bars else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "lien_turn_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("lien_turn_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    timeframe = str(first(state, "lien_turn_timeframe") or "").strip().lower()
    entry_time = _valid_hhmm(first(state, "lien_turn_entry_time_ny"))
    entry = number(first(state, "lien_turn_entry_price"))
    pip_size = number(first(state, "lien_turn_pip_size"))
    bars = _daily_bars(first(state, "lien_turn_daily_bars"))
    if timeframe not in {"daily", "day", "daily chart"}:
        result["lien_turn_action"] = "INVALID_TURN_TIMEFRAME"
        result["reasons"] = ["the source extension statistic is defined on daily candles"]
        return result
    if entry_time is None or entry is None or entry <= 0 or pip_size is None or pip_size <= 0:
        result["lien_turn_action"] = "INVALID_TURN_PARAMETERS"
        result["reasons"] = ["the extension turn requires a positive entry and pip size plus a valid New York time"]
        return result
    if bars is None or len(bars) < 7:
        result["lien_turn_action"] = "INSUFFICIENT_DAILY_EXTENSION"
        result["reasons"] = ["the extension turn needs seven completed daily candles"]
        return result
    if entry_time != 1700:
        result["lien_turn_action"] = "WAIT_FOR_1700_NEW_YORK_ENTRY"
        result["reasons"] = ["the source enters when the next daily candle begins at 5 p.m. New York time"]
        return result

    extension = bars[-7:]
    weakness = all(closing < opening for opening, closing in extension)
    strength = all(closing > opening for opening, closing in extension)
    result["lien_turn_consecutive_days"] = 7
    result["lien_turn_extension_state"] = "WEAKNESS" if weakness else "STRENGTH" if strength else "NONE"
    if not weakness and not strength:
        result["lien_turn_action"] = "NO_SEVEN_DAY_EXTENSION"
        result["reasons"] = ["the latest seven daily candles are not all weak or all strong"]
        return result

    selected_side = "BUY" if weakness else "SELL"
    risk_pips = 30
    scale_out_pips = 2 * risk_pips
    final_target_pips = 4 * risk_pips
    stop = entry - risk_pips * pip_size if selected_side == "BUY" else entry + risk_pips * pip_size
    scale_out = entry + scale_out_pips * pip_size if selected_side == "BUY" else entry - scale_out_pips * pip_size
    final_target = entry + final_target_pips * pip_size if selected_side == "BUY" else entry - final_target_pips * pip_size
    if stop <= 0 or scale_out <= 0 or final_target <= 0:
        result["lien_turn_action"] = "INVALID_TURN_GEOMETRY"
        result["reasons"] = ["the fixed 30/60/120 pip plan does not produce positive prices"]
        return result
    result.update(
        {
            "lien_turn_action": "BUY_EXTENSION_TURN" if selected_side == "BUY" else "SELL_EXTENSION_TURN",
            "lien_turn_selected_side": selected_side,
            "lien_turn_risk_pips": risk_pips,
            "lien_turn_stop_price": stop,
            "lien_turn_scale_out_pips": scale_out_pips,
            "lien_turn_scale_out_price": scale_out,
            "lien_turn_final_target_pips": final_target_pips,
            "lien_turn_final_target_price": final_target,
            "lien_turn_stop_formula": "entry +/- 30 pips; scale half at 2R; final at 4R/120 pips",
            "directional_claim": True,
        }
    )
    return with_direction(
        result,
        state,
        selected_side,
        "seven consecutive weak/strong daily candles triggered the source short-term turn plan",
    )
