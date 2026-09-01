"""Kathy Lien's five-moving-average perfect-order trend checklist."""
from __future__ import annotations

from ._common import absent, base, first, number, values, with_direction

ALGORITHM_ID = "lien_perfect_order"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_ma_10",
    "lien_ma_20",
    "lien_ma_50",
    "lien_ma_100",
    "lien_ma_200",
    "lien_adx",
    "lien_adx_rising",
    "lien_formation_age_candles",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = str(value or "").strip().lower()
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
    ma = [number(first(state, key)) for key in ("lien_ma_10", "lien_ma_20", "lien_ma_50", "lien_ma_100", "lien_ma_200")]
    adx = number(first(state, "lien_adx"))
    age = number(first(state, "lien_formation_age_candles"))
    if any(value is None for value in ma) or adx is None or age is None:
        result["reasons"] = ["moving averages, ADX, and formation age must be finite observations"]
        return result
    if adx <= 20 or first(state, "lien_adx_rising") is not True:
        result["reasons"] = ["the perfect-order filter requires ADX above 20 and rising"]
        return result
    if age < 5:
        result["reasons"] = ["the source entry is five candles after initial formation"]
        return result
    signal = "BUY" if ma[0] > ma[1] > ma[2] > ma[3] > ma[4] else "SELL" if ma[0] < ma[1] < ma[2] < ma[3] < ma[4] else None
    if signal is None:
        result["reasons"] = ["the moving averages are not in sequential perfect order"]
        return result
    return with_direction(result, state, signal, "five moving averages are stacked and rising ADX confirms a trend")
