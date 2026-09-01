"""Coulling/Wyckoff trend-level effort-versus-result perspective."""
from __future__ import annotations

from ._common import base, first, normalized_status, number, vpa_missing, vpa_real_volume, with_direction

ALGORITHM_ID = "vpa_trend_effort_confirmation"
SOURCES = ("Anna Coulling — A Complete Guide To Volume Price Analysis",)
KEYS = (
    "vpa_trend_direction",
    "vpa_trend_price_change",
    "vpa_trend_volume_change",
    "vpa_trend_bars",
    "vpa_volume_provenance",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = vpa_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not vpa_real_volume(state):
        result["view"] = "WAIT"
        result["warnings"] = ["tick-volume proxies cannot validate trend-level effort versus result"]
        result["reasons"] = ["real traded volume is unavailable"]
        return result
    trend = normalized_status(first(state, "vpa_trend_direction"))
    price_change = number(first(state, "vpa_trend_price_change"))
    volume_change = number(first(state, "vpa_trend_volume_change"))
    bars = number(first(state, "vpa_trend_bars"))
    if trend not in {"up", "down"} or price_change is None or volume_change is None or bars is None or bars < 2 or price_change == 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["trend effort requires a non-zero directional price change and at least two completed bars"]
        return result
    result["analysis_stage"] = "causal_trend_effort_result"
    result["vpa_trend_price_change"] = price_change
    result["vpa_trend_volume_change"] = volume_change
    result["vpa_trend_bars"] = int(bars)
    aligned = (trend == "up" and price_change > 0) or (trend == "down" and price_change < 0)
    expanding = volume_change > 0
    if aligned and expanding:
        result["vpa_trend_effort_assessment"] = f"{trend.upper()}TREND_EFFORT_CONFIRMED"
        return with_direction(result, state, "BUY" if trend == "up" else "SELL", "trend price movement is accompanied by increasing real traded volume")
    result["vpa_trend_effort_assessment"] = f"{trend.upper()}TREND_EFFORT_ANOMALY"
    result["directional_claim"] = False
    result["warnings"] = ["price-volume disagreement is a weakness/strength warning, not an automatic reversal signal"]
    result["reasons"] = ["trend result is not accompanied by expanding volume effort"]
    return result
