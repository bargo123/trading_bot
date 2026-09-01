"""Adam Grimes' three-push exhaustion warning."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "grimes_three_push_exhaustion"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis",)
KEYS = (
    "grimes_trend_direction",
    "grimes_push_prices",
    "grimes_push_bar_indexes",
    "grimes_trendline_break",
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


def _symmetric_ratio(values_: list[float]) -> float | None:
    gaps = [abs(values_[index] - values_[index - 1]) for index in range(1, len(values_))]
    if not gaps or any(gap <= 0.0 for gap in gaps):
        return None
    return max(gaps) / min(gaps)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "grimes_data_provenance")):
        missing.append("grimes_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "grimes_trend_direction"))
    trend_direction = "up" if trend in {"up", "uptrend", "bull", "bullish"} else "down" if trend in {"down", "downtrend", "bear", "bearish"} else None
    prices = first(state, "grimes_push_prices")
    indexes = first(state, "grimes_push_bar_indexes")
    if trend_direction is None or not isinstance(prices, (list, tuple)) or not isinstance(indexes, (list, tuple)) or len(prices) < 3 or len(indexes) < 3:
        result["reasons"] = ["three-push analysis needs a directional trend and three causal swing observations"]
        return with_direction(result, state, None, "three-push exhaustion is a warning, not an entry signal")

    push_prices = [number(value) for value in prices[-3:]]
    push_indexes = [number(value) for value in indexes[-3:]]
    if any(value is None for value in (*push_prices, *push_indexes)):
        result["reasons"] = ["push prices and bar indexes must be finite numeric observations"]
        return with_direction(result, state, None, "three-push exhaustion is a warning, not an entry signal")
    assert push_prices and push_indexes
    prices_ordered = all(push_prices[i] > push_prices[i - 1] for i in range(1, 3)) if trend_direction == "up" else all(push_prices[i] < push_prices[i - 1] for i in range(1, 3))
    indexes_ordered = all(push_indexes[i] > push_indexes[i - 1] for i in range(1, 3))
    time_ratio = _symmetric_ratio(push_indexes)
    price_ratio = _symmetric_ratio(push_prices)
    if not prices_ordered or not indexes_ordered or time_ratio is None or price_ratio is None or time_ratio > 2.5 or price_ratio > 2.5:
        result["reasons"] = ["the three pushes are not ordered and reasonably symmetric in price and time"]
        return with_direction(result, state, None, "three-push exhaustion is a warning, not an entry signal")

    result.update(
        {
            "grimes_push_direction": trend_direction.upper(),
            "grimes_push_prices": push_prices,
            "grimes_push_bar_indexes": push_indexes,
            "grimes_push_spacing_ratio": time_ratio,
            "grimes_push_price_spacing_ratio": price_ratio,
            "grimes_exhaustion_warning": False,
        }
    )
    if not _truth(first(state, "grimes_trendline_break")):
        result["reasons"] = ["three pushes are present, but the observed trendline has not broken"]
        return with_direction(result, state, None, "three-push exhaustion is a warning, not a countertrend entry")

    result["grimes_exhaustion_warning"] = True
    result["reasons"] = ["three roughly symmetric pushes and a trendline break warn of short-term exhaustion"]
    return with_direction(result, state, None, "exhaustion does not authorize a countertrend entry")
