"""Gray--Vogel time-series momentum overlay for portfolio risk context."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values


ALGORITHM_ID = "gray_vogel_time_series_overlay"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_overlay_current_price",
    "gray_overlay_sma",
    "gray_overlay_market_return",
    "gray_overlay_risk_free_return",
    "gray_overlay_lookback_months",
    "gray_overlay_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable")) and any(
        token in label for token in ("observed", "measured", "historical")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_overlay_data_provenance")):
        missing.append("gray_overlay_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    current = number(first(state, "gray_overlay_current_price"))
    sma = number(first(state, "gray_overlay_sma"))
    market_return = number(first(state, "gray_overlay_market_return"))
    risk_free = number(first(state, "gray_overlay_risk_free_return"))
    lookback = number(first(state, "gray_overlay_lookback_months"))
    if any(value is None for value in (current, sma, market_return, risk_free, lookback)) or current <= 0.0 or sma <= 0.0 or lookback != 12.0:
        result["gray_overlay_action"] = "INVALID_OVERLAY_INPUT"
        result["reasons"] = ["the overlay requires positive prices, finite returns, and the source 12-month lookback"]
        return result
    risk_on = current > sma and market_return > risk_free
    result["gray_overlay_action"] = "RISK_ON_OVERLAY" if risk_on else "DEFENSIVE_OVERLAY"
    result["reasons"] = [
        "the observed market is above its 12-month average and its return exceeds the risk-free return"
        if risk_on
        else "the observed market fails the 12-month trend or excess-return condition and should use the defensive sleeve"
    ]
    return result
