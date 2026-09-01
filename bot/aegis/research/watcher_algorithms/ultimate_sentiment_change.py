"""Anna Coulling's recent broker-sentiment-evolution perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_sentiment_change"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_sentiment_previous_long_pct",
    "ultimate_sentiment_previous_short_pct",
    "ultimate_sentiment_current_long_pct",
    "ultimate_sentiment_current_short_pct",
    "ultimate_sentiment_interval_hours",
    "ultimate_sentiment_min_change_pct",
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
    numbers = [number(first(state, key)) for key in KEYS[:-1]]
    previous_long, previous_short, current_long, current_short, interval, minimum_change = numbers
    if any(value is None for value in numbers) or any(not 0 <= value <= 100 for value in numbers[:4]):
        result["view"] = "WAIT"
        result["ultimate_sentiment_assessment"] = "SENTIMENT_VALUES_INVALID"
        result["reasons"] = ["sentiment percentages must be finite values between zero and one hundred"]
        return result
    if abs(previous_long + previous_short - 100.0) > 1.0 or abs(current_long + current_short - 100.0) > 1.0:
        result["view"] = "WAIT"
        result["ultimate_sentiment_assessment"] = "SENTIMENT_TOTAL_INVALID"
        result["reasons"] = ["long and short sentiment shares must each sum to approximately one hundred"]
        return result
    if interval <= 0 or minimum_change <= 0:
        result["view"] = "WAIT"
        result["ultimate_sentiment_assessment"] = "SENTIMENT_WINDOW_INVALID"
        result["reasons"] = ["sentiment evolution needs a positive observation interval and change threshold"]
        return result
    change = current_long - previous_long
    result["ultimate_sentiment_change_pct"] = change
    result["ultimate_sentiment_complementary_only"] = True
    if abs(change) < minimum_change:
        result["view"] = "WAIT"
        result["ultimate_sentiment_assessment"] = "CHANGE_NOT_MATERIAL"
        result["reasons"] = ["the recent sentiment evolution is below the observed material-change threshold"]
        return result
    signal = "BUY" if change > 0 else "SELL"
    result["ultimate_sentiment_assessment"] = "RECENT_SENTIMENT_EVOLUTION"
    return with_direction(result, state, signal, "the recent change in sentiment, not its absolute level, supplies the directional context")
