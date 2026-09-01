"""Range-conditioned mean-reversion perspective using explicit displacement."""
from __future__ import annotations

from ._common import base, direction, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "mean_reversion"
SOURCES = (
    "Ernest Chan — Quantitative Trading",
    "Andrew Pole — Statistical Arbitrage",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "regime",
    "range_state",
    "zscore",
    "spread_zscore",
    "distance_from_mean",
    "mean_reversion_signal",
)


def _negative_label(value) -> bool:
    normalized = normalized_status(value)
    return any(
        marker in normalized
        for marker in (
            "not ", "no ", "without ", "unconfirmed", "failed", "invalid",
            "unknown", "neutral", "ambiguous",
        )
    )


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            applicability="MISSING_DATA",
            view="MISSING_DATA",
            missing_inputs=("range_regime_and_displacement",),
        )
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    regime = normalized_status(first(state, "range_state", "regime"))
    if not regime:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["range_regime"]
        result["reasons"] = ["mean reversion requires an explicit range or balance regime"]
        return result
    if any(token in regime for token in ("trend", "trending", "initiative")) and not any(token in regime for token in ("range", "balance")):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["mean reversion is not applicable in an explicit trend regime"]
        return result
    if not any(token in regime for token in ("range", "range bound", "balanced", "balance")):
        result["view"] = "WAIT"
        result["reasons"] = ["regime is neither an explicit range nor a supported mean-reversion state"]
        return result

    zscore = number(first(state, "zscore", "spread_zscore", "distance_from_mean"))
    signal = None
    explicit_signal = first(state, "mean_reversion_signal")
    if explicit_signal is not None:
        if _negative_label(explicit_signal):
            result["view"] = "WAIT"
            result["reasons"] = ["mean-reversion signal is negated or unresolved"]
            return result
        signal = direction(explicit_signal)
        if signal is None:
            result["view"] = "WAIT"
            result["reasons"] = ["mean-reversion signal direction is unavailable"]
            return result
    elif zscore is not None and abs(zscore) >= 2.0:
        signal = "BUY" if zscore < 0 else "SELL"
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["range displacement is absent or below the explicit reversion threshold"]
        return result
    result = with_direction(result, state, signal, "range regime and measured displacement support a mean-reversion test")
    if zscore is not None:
        result["zscore"] = zscore
    return result
