"""López de Prado volume-runs-bar event diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_bars_common import positive_series, run_events, tick_signs
from ._deprado_common import provenance_ok

ALGORITHM_ID = "deprado_volume_runs_bar"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_runs_prices",
    "deprado_volume_run_values",
    "deprado_runs_expected_bar_size",
    "deprado_runs_buy_probability",
    "deprado_runs_buy_mean",
    "deprado_runs_sell_mean",
    "deprado_runs_data_provenance",
)


def evaluate(state):
    prices = positive_series(state, "deprado_runs_prices")
    amounts = positive_series(state, "deprado_volume_run_values")
    bar_size = number(first(state, "deprado_runs_expected_bar_size"))
    buy_probability = number(first(state, "deprado_runs_buy_probability"))
    buy_mean = number(first(state, "deprado_runs_buy_mean"))
    sell_mean = number(first(state, "deprado_runs_sell_mean"))
    found = values(state, *KEYS)
    missing = []
    for key, value in (
        ("deprado_runs_prices", prices),
        ("deprado_volume_run_values", amounts),
        ("deprado_runs_expected_bar_size", bar_size),
        ("deprado_runs_buy_probability", buy_probability),
        ("deprado_runs_buy_mean", buy_mean),
        ("deprado_runs_sell_mean", sell_mean),
    ):
        if value is None:
            missing.append(key)
    provenance = first(state, "deprado_runs_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_runs_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if len(prices) != len(amounts) or bar_size <= 0 or not 0 <= buy_probability <= 1 or buy_mean <= 0 or sell_mean <= 0:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["volume runs inputs must be aligned, positive, and bounded"]
        return result

    expected = bar_size * max(buy_probability * buy_mean, (1 - buy_probability) * sell_mean)
    events = run_events(tick_signs(prices), amounts, expected)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_event_sampling"
    result["deprado_volume_runs_expected"] = expected
    result["deprado_volume_runs_events"] = events
    result["deprado_volume_runs_event_count"] = len(events)
    result["deprado_volume_runs_assessment"] = "VOLUME_RUN_EVENTS_MEASURED"
    result["warnings"] = ["volume runs bars sample one-sided activity; they do not authorize a trade"]
    return result
