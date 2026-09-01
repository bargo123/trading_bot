"""Marcel Link's ADX regime switch and trend-strength perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_adx_regime_switch"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_adx_value",
    "link_adx_direction",
    "link_major_trend_direction",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    adx = number(first(state, "link_adx_value"))
    adx_direction = normalized_status(first(state, "link_adx_direction"))
    trend = normalized_status(first(state, "link_major_trend_direction")).upper()
    candidate_side = side(state)
    if adx is None or not 0.0 <= adx <= 100.0 or trend not in {"BUY", "SELL"}:
        result["link_adx_mode"] = "INVALID_INPUT"
        result["reasons"] = ["ADX and the major trend direction must be finite observed values"]
        return result

    result["link_adx_value"] = adx
    result["link_major_trend_direction"] = trend
    if adx >= 30.0:
        if adx_direction in {"falling", "declining", "decreasing"}:
            result["link_adx_mode"] = "TREND_WEAKENING"
            result["reasons"] = ["ADX is at a strong-trend level but is declining, so continuation should not be assumed"]
            return result
        if adx_direction not in {"rising", "increasing", "strong"}:
            result["link_adx_mode"] = "STRONG_TREND_UNCONFIRMED"
            result["reasons"] = ["ADX is high but its strengthening direction is not observed"]
            return result
        result["link_adx_mode"] = "TREND_FOLLOWING"
        if candidate_side != trend:
            result["reasons"] = ["a strong ADX regime favors the major trend and opposes this candidate side"]
            return result
        return with_direction(result, state, trend, "rising ADX supports trading with the observed major trend")

    if adx <= 20.0:
        result["link_adx_mode"] = "OSCILLATOR_RANGE"
        result["reasons"] = ["low ADX identifies a choppy/range-bound regime where oscillator evidence is preferred"]
        return result

    result["link_adx_mode"] = "TRANSITIONAL"
    result["reasons"] = ["ADX lies between the source's range and strong-trend zones"]
    return result
