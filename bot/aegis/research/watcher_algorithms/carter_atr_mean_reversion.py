"""John Carter's 13/21-EMA and ATR extension-to-mean perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "carter_atr_mean_reversion"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_mean_timeframe",
    "carter_mean_price",
    "carter_mean_ema13",
    "carter_mean_ema21",
    "carter_mean_atr14",
    "carter_mean_band_multiple",
    "carter_mean_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_mean_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_mean_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    timeframe = normalized_status(first(state, "carter_mean_timeframe"))
    if timeframe not in {"daily", "weekly"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the source extension rule is for daily or weekly mean-price context"]
        return result
    price = number(first(state, "carter_mean_price"))
    ema13 = number(first(state, "carter_mean_ema13"))
    ema21 = number(first(state, "carter_mean_ema21"))
    atr = number(first(state, "carter_mean_atr14"))
    band_multiple = number(first(state, "carter_mean_band_multiple"))
    if any(value is None for value in (price, ema13, ema21, atr, band_multiple)) or atr <= 0:
        result["reasons"] = ["price, 13/21 EMAs, ATR(14), and band multiple must be finite with positive ATR"]
        return result
    if abs(band_multiple - 1.5) > 1e-9:
        result["reasons"] = ["the observed Keltner-style band multiple is not the source 1.5 ATR configuration"]
        return result
    mean = (ema13 + ema21) / 2.0
    extension = (price - mean) / atr
    result["carter_mean_extension_atr"] = extension
    if extension >= 1.0:
        signal = "SELL"
    elif extension <= -1.0:
        signal = "BUY"
    else:
        result["reasons"] = ["price has not extended approximately one ATR beyond the 13/21 EMA mean zone"]
        return result
    return with_direction(result, state, signal, "price is observed at an ATR-sized extension from the adaptive 13/21 EMA mean zone")
