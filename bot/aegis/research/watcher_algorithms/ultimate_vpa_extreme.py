"""The Ultimate Forex Trading System's volume-price extreme study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_vpa_extreme"
SOURCES = ("Mostafa Afshari — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_vpa_timeframe",
    "ultimate_vpa_volume_event",
    "ultimate_vpa_price_location",
    "ultimate_vpa_volume_ratio",
    "ultimate_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    timeframe = normalized_status(first(state, "ultimate_vpa_timeframe"))
    event = normalized_status(first(state, "ultimate_vpa_volume_event"))
    location = normalized_status(first(state, "ultimate_vpa_price_location"))
    ratio = number(first(state, "ultimate_vpa_volume_ratio"))
    if timeframe not in {"1h", "4h", "1 hour", "4 hour"} or ratio is None or ratio <= 1:
        result["ultimate_vpa_assessment"] = "VOLUME_EVENT_INVALID"
        result["reasons"] = ["the source VPA proxy requires a current 1H/4H volume increase over the prior bar"]
        return result
    if event == "spike" and location in {"daily high resistance", "daily high", "resistance"}:
        result["ultimate_vpa_assessment"] = "SPIKE_AT_RESISTANCE"
        return with_direction(result, state, "SELL", "a volume spike at a daily high/resistance is the source's reversal warning")
    if event == "spike" and location in {"daily low support", "daily low", "support"}:
        result["ultimate_vpa_assessment"] = "SPIKE_AT_SUPPORT"
        return with_direction(result, state, "BUY", "a volume spike at a daily low/support is the source's reversal warning")
    if event in {"slight rise", "rise", "increasing"}:
        direction = normalized_status(first(state, "ultimate_vpa_trend_direction"))
        if direction in {"up", "upward", "bull", "bullish", "buy", "long"}:
            result["ultimate_vpa_assessment"] = "RISE_CONFIRMS_UPTREND"
            return with_direction(result, state, "BUY", "a modest volume rise confirms the observed uptrend")
        if direction in {"down", "downward", "bear", "bearish", "sell", "short"}:
            result["ultimate_vpa_assessment"] = "RISE_CONFIRMS_DOWNTREND"
            return with_direction(result, state, "SELL", "a modest volume rise confirms the observed downtrend")
    result["ultimate_vpa_assessment"] = "LOCATION_OR_EVENT_UNSUPPORTED"
    result["reasons"] = ["the volume event and price location do not form a source-defined VPA interpretation"]
    return result
