"""Kathy Lien's daily-range fader for screened false breakouts."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_fader"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_adx",
    "lien_adx_trend",
    "lien_previous_day_low_break_pips",
    "lien_previous_day_high_break_pips",
    "lien_previous_day_high_reclaim_pips",
    "lien_previous_day_low_reclaim_pips",
    "lien_stop_pips",
    "lien_target_risk_multiple",
    "lien_target_pips",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    candidate_side = side(state)
    required = ["lien_adx", "lien_adx_trend", "lien_stop_pips"]
    if candidate_side == "BUY":
        required.extend(("lien_previous_day_low_break_pips", "lien_previous_day_high_reclaim_pips"))
    elif candidate_side == "SELL":
        required.extend(("lien_previous_day_high_break_pips", "lien_previous_day_low_reclaim_pips"))
    else:
        required.extend(("lien_previous_day_low_break_pips", "lien_previous_day_high_reclaim_pips"))
    if first(state, "lien_target_risk_multiple") is None and first(state, "lien_target_pips") is None:
        required.append("lien_target_risk_multiple_or_target_pips")
    missing = [key for key in required if first(state, key) is None]
    if not _provenance_ok(first(state, "lien_data_provenance")):
        missing.append("lien_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    adx = number(first(state, "lien_adx"))
    stop_pips = number(first(state, "lien_stop_pips"))
    target_r = number(first(state, "lien_target_risk_multiple"))
    target_pips = number(first(state, "lien_target_pips"))
    if adx is None or not 0 <= adx < 35:
        result["reasons"] = ["the fader requires a 14-period ADX below 35"]
        return result
    if stop_pips is None or not 0 < stop_pips <= 30:
        result["reasons"] = ["the initial fader stop must be no more than 30 pips"]
        return result
    if (target_r is None or target_r < 2) and (target_pips is None or target_pips < 60):
        result["reasons"] = ["the exit plan must provide at least 2R or the source 60-pip objective"]
        return result
    if normalized_status(first(state, "lien_adx_trend")) not in {"falling", "down", "declining"}:
        result["warnings"] = ["ADX is below 35 but is not observed falling"]
    signal = None
    if candidate_side == "BUY":
        low_break = number(first(state, "lien_previous_day_low_break_pips"))
        high_reclaim = number(first(state, "lien_previous_day_high_reclaim_pips"))
        if low_break is not None and high_reclaim is not None and low_break >= 15 and high_reclaim >= 15:
            signal = "BUY"
    elif candidate_side == "SELL":
        high_break = number(first(state, "lien_previous_day_high_break_pips"))
        low_reclaim = number(first(state, "lien_previous_day_low_reclaim_pips"))
        if high_break is not None and low_reclaim is not None and high_break >= 15 and low_reclaim >= 15:
            signal = "SELL"
    if signal is None:
        result["reasons"] = ["the previous-day extreme has not produced the required 15-pip false break and reversal"]
        return result
    return with_direction(result, state, signal, "weak ADX and a two-sided previous-day false breakout support the fade")
