"""López de Prado dollar-imbalance-bar event diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_bars_common import imbalance_events, positive_series, tick_signs
from ._deprado_common import provenance_ok

ALGORITHM_ID = "deprado_dollar_imbalance_bar"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_imbalance_prices",
    "deprado_dollar_values",
    "deprado_imbalance_expected_bar_size",
    "deprado_imbalance_buy_probability",
    "deprado_imbalance_buy_mean",
    "deprado_imbalance_sell_mean",
    "deprado_imbalance_data_provenance",
)


def evaluate(state):
    prices = positive_series(state, "deprado_imbalance_prices")
    amounts = positive_series(state, "deprado_dollar_values")
    bar_size = number(first(state, "deprado_imbalance_expected_bar_size"))
    buy_probability = number(first(state, "deprado_imbalance_buy_probability"))
    buy_mean = number(first(state, "deprado_imbalance_buy_mean"))
    sell_mean = number(first(state, "deprado_imbalance_sell_mean"))
    found = values(state, *KEYS)
    missing = []
    for key, value in (
        ("deprado_imbalance_prices", prices),
        ("deprado_dollar_values", amounts),
        ("deprado_imbalance_expected_bar_size", bar_size),
        ("deprado_imbalance_buy_probability", buy_probability),
        ("deprado_imbalance_buy_mean", buy_mean),
        ("deprado_imbalance_sell_mean", sell_mean),
    ):
        if value is None:
            missing.append(key)
    provenance = first(state, "deprado_imbalance_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_imbalance_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if len(prices) != len(amounts) or bar_size <= 0 or not 0 <= buy_probability <= 1 or buy_mean <= 0 or sell_mean <= 0:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["dollar imbalance inputs must be aligned, positive, and bounded"]
        return result

    expected = bar_size * abs(buy_probability * buy_mean - (1 - buy_probability) * sell_mean)
    events = imbalance_events(tick_signs(prices), amounts, expected)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_event_sampling"
    result["deprado_dollar_expected_imbalance"] = expected
    result["deprado_dollar_imbalance_events"] = events
    result["deprado_dollar_event_count"] = len(events)
    result["deprado_dollar_imbalance_assessment"] = "DOLLAR_IMBALANCE_EVENTS_MEASURED"
    result["warnings"] = ["dollar imbalance bars sample activity; they do not authorize a trade"]
    return result
