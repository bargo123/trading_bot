"""Coulling's low-volume long-legged-doji anomaly filter."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, vpa_missing, vpa_real_volume

ALGORITHM_ID = "vpa_long_legged_doji"
SOURCES = ("Anna Coulling — A Complete Guide To Volume Price Analysis",)
KEYS = (
    "vpa_setup", "vpa_candle_range_pips", "vpa_candle_body_fraction",
    "vpa_volume_ratio", "vpa_volume_provenance",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = vpa_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if normalized_status(first(state, "vpa_setup")) != "long legged doji":
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed candle is not a long-legged doji"]
        return result
    if not vpa_real_volume(state):
        result["warnings"] = ["tick-volume proxy cannot validate a VPA volume anomaly"]
        result["view"] = "WAIT"
        result["reasons"] = ["real traded volume is unavailable"]
        return result
    width = number(first(state, "vpa_candle_range_pips"))
    body = number(first(state, "vpa_candle_body_fraction"))
    volume = number(first(state, "vpa_volume_ratio"))
    if width is None or body is None or volume is None or width < 10.0 or body > 0.2 or volume >= 0.8:
        result["view"] = "WAIT"
        result["reasons"] = ["wide range with low effort is not confirmed"]
        return result
    result["view"] = "WAIT"
    result["warnings"] = ["low-volume wide-range doji is an anomaly; wait for validation"]
    result["reasons"] = ["VPA identifies possible stop-hunting or news-driven manipulation"]
    return result
