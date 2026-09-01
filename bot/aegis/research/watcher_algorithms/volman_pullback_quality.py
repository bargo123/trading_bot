"""Bob Volman's pullback-quality distinction for continuation setup studies."""
from __future__ import annotations

from ._common import absent, base, first, number, normalized_status, side, values, volman_direction, volman_missing, with_direction


ALGORITHM_ID = "volman_pullback_quality"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "side",
    "volman_trend",
    "volman_signal_direction",
    "volman_pullback_style",
    "volman_pullback_fraction",
    "volman_setup",
)

_SETUPS = {"double doji break", "first break", "second break", "block break", "range break", "inside range break", "advanced range break"}
_GOOD_STYLES = {"diagonal", "substantial", "thin horizontal"}
_CAUTION_STYLES = {"clustering", "clustered", "scribbling", "horizontal"}


def evaluate(state):
    found = values(state, *KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = True
    candidate_side = side(state)
    trend = normalized_status(first(state, "volman_trend"))
    signal = volman_direction(state)
    style = normalized_status(first(state, "volman_pullback_style"))
    fraction = number(first(state, "volman_pullback_fraction"))
    setup = normalized_status(first(state, "volman_setup"))
    if candidate_side not in {"BUY", "SELL"} or trend not in {"up", "down"} or signal not in {"up", "down"} or setup not in _SETUPS or fraction is None or not 0.0 < fraction < 1.0:
        result["volman_pullback_assessment"] = "INVALID_PULLBACK_INPUT"
        result["reasons"] = ["trend, setup, pullback style, fraction, and directional signal must be explicit source-compatible observations"]
        return result
    expected = "up" if candidate_side == "BUY" else "down"
    if trend != expected or signal != expected:
        result["volman_pullback_assessment"] = "COUNTERTREND_PULLBACK"
        result["reasons"] = ["the continuation pullback is not aligned with the observed trend and signal direction"]
        return result
    if style in _CAUTION_STYLES:
        result["volman_pullback_assessment"] = "CLUSTERED_PULLBACK_CAUTION"
        result["reasons"] = ["scribbling or clustered pullbacks carry less continuation information and require caution"]
        return result
    if style not in _GOOD_STYLES:
        result["volman_pullback_assessment"] = "UNSUPPORTED_PULLBACK_STYLE"
        result["reasons"] = ["the pullback style is not one of the source's observed quality categories"]
        return result
    result["volman_pullback_assessment"] = "QUALITY_CONTINUATION_PULLBACK"
    result["volman_pullback_fraction"] = fraction
    return with_direction(result, state, candidate_side, "diagonal, substantial, or thin horizontal pullback supports a continuation study")
