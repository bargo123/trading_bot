"""Adam Grimes' higher-timeframe pullback quality study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "grimes_pullback_quality"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis",)
KEYS = (
    "grimes_trend_direction",
    "grimes_pullback_direction",
    "grimes_impulse_strength",
    "grimes_momentum_divergence",
    "grimes_retracement_percent",
    "grimes_pullback_volatility_relative",
    "grimes_continuation_confirmed",
    "grimes_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present"}


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "grimes_data_provenance")):
        missing.append("grimes_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "grimes_trend_direction"))
    pullback = normalized_status(first(state, "grimes_pullback_direction"))
    trend_direction = "up" if trend in {"up", "uptrend", "bull", "bullish"} else "down" if trend in {"down", "downtrend", "bear", "bearish"} else None
    pullback_direction = "up" if pullback in {"up", "uptrend", "bull", "bullish"} else "down" if pullback in {"down", "downtrend", "bear", "bearish"} else None
    if trend_direction is None or pullback_direction != ("down" if trend_direction == "up" else "up"):
        result["reasons"] = ["the pullback must counter the observed higher-timeframe trend"]
        return result

    impulse = normalized_status(first(state, "grimes_impulse_strength"))
    if impulse not in {"significant", "strong", "impulse", "new high", "new low", "confirmed"}:
        result["reasons"] = ["a significant impulse must precede the pullback"]
        return result
    if _truth(first(state, "grimes_momentum_divergence")):
        result["reasons"] = ["momentum divergence weakens the pullback continuation case"]
        return result

    retracement = number(first(state, "grimes_retracement_percent"))
    if retracement is None or not 25.0 <= retracement <= 75.0:
        result["reasons"] = ["the observed pullback retracement is outside the 25-75 percent quality range"]
        return result
    relative_volatility = number(first(state, "grimes_pullback_volatility_relative"))
    if relative_volatility is None or not 0.0 < relative_volatility <= 1.0:
        result["reasons"] = ["the pullback should show lower activity and volatility than the impulse"]
        return result
    if not _truth(first(state, "grimes_continuation_confirmed")):
        result["reasons"] = ["continuation has not been confirmed after the pullback"]
        return result

    result.update(
        {
            "grimes_trend_direction": trend_direction,
            "grimes_pullback_direction": pullback_direction,
            "grimes_retracement_percent": retracement,
            "grimes_pullback_volatility_relative": relative_volatility,
        }
    )
    signal = "BUY" if trend_direction == "up" else "SELL"
    return with_direction(result, state, signal, "trend-aligned impulse, controlled pullback, and continuation confirmation agree")
