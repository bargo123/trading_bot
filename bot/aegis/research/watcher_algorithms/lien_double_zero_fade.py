"""Kathy Lien's quiet-market double-zero fade checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_double_zero_fade"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_market_condition",
    "lien_round_number_distance_pips",
    "lien_price_vs_intraday_sma20",
    "lien_round_number_confluence",
    "lien_stop_pips",
    "lien_target_risk_multiple",
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
    if normalized_status(first(state, "lien_market_condition")) != "quiet":
        result["reasons"] = ["the double-zero fade is intended for quiet conditions"]
        return result
    candidate_side = side(state)
    distance = number(first(state, "lien_round_number_distance_pips"))
    sma_displacement = number(first(state, "lien_price_vs_intraday_sma20"))
    stop_pips = number(first(state, "lien_stop_pips"))
    target_r = number(first(state, "lien_target_risk_multiple"))
    if candidate_side not in {"BUY", "SELL"} or distance is None or sma_displacement is None:
        result["reasons"] = ["side, round-number distance, and SMA displacement must be observed"]
        return result
    if stop_pips is None or not 0 < stop_pips <= 20:
        result["reasons"] = ["the initial stop must be positive and no more than 20 pips"]
        return result
    if target_r is None or target_r < 2:
        result["reasons"] = ["the source plan requires a first profit objective of at least 2R"]
        return result
    if first(state, "lien_round_number_confluence") is not True:
        result["reasons"] = ["the round number lacks an observed technical confluence"]
        return result
    signal = None
    if candidate_side == "BUY" and -10 <= distance < 0 and sma_displacement < 0:
        signal = "BUY"
    elif candidate_side == "SELL" and 0 < distance <= 10 and sma_displacement > 0:
        signal = "SELL"
    if signal is None:
        result["reasons"] = ["price is not fading a round number from the required side of the intraday SMA"]
        return result
    result.update({"lien_round_number_fade": True, "lien_stop_pips": stop_pips, "lien_target_r": target_r})
    return with_direction(result, state, signal, "quiet double-zero level has SMA displacement and technical confluence")
