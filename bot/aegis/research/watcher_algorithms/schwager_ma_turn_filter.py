"""Moving-average turn with Schwager's trend/range distinction."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_ma_turn_filter"
SOURCES = ("Getting Started in Technical Analysis",)
KEYS = (
    "schwager_ma_current",
    "schwager_ma_previous",
    "schwager_ma_minimum_turn",
    "schwager_market_regime",
    "schwager_ma_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and "moving average" in label


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_ma_data_provenance")):
        missing.append("schwager_ma_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    current = number(first(state, "schwager_ma_current"))
    previous = number(first(state, "schwager_ma_previous"))
    minimum = number(first(state, "schwager_ma_minimum_turn"))
    regime = normalized_status(first(state, "schwager_market_regime"))
    if None in {current, previous, minimum} or minimum <= 0:
        result["schwager_ma_assessment"] = "UNKNOWN"
        result["reasons"] = ["moving-average turn requires finite values and a positive supplied reversal amount"]
        return result
    delta = current - previous
    result["schwager_ma_turn"] = delta
    if regime in {"range", "sideways", "chop", "choppy"}:
        result["schwager_ma_assessment"] = "RANGE_WHIPSAW_RISK"
        result["reasons"] = ["the source warns that moving-average turns generate false signals in choppy ranges"]
        return result
    if regime not in {"trend", "trending", "uptrend", "downtrend"} or abs(delta) < minimum:
        result["schwager_ma_assessment"] = "INSUFFICIENT_TURN"
        result["reasons"] = ["the observed moving-average turn does not meet its supplied minimum in a trend regime"]
        return result
    result["schwager_ma_assessment"] = "CONFIRMED_TREND_TURN"
    signal = "BUY" if delta > 0 else "SELL"
    return with_direction(result, state, signal, "the moving average turned by the supplied minimum while the market was classified as trending")
