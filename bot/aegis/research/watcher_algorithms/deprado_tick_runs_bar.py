"""López de Prado tick-runs-bar event diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_bars_common import positive_series, run_events, tick_signs
from ._deprado_common import provenance_ok

ALGORITHM_ID = "deprado_tick_runs_bar"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_runs_prices",
    "deprado_runs_expected_bar_size",
    "deprado_runs_buy_probability",
    "deprado_runs_data_provenance",
)


def evaluate(state):
    prices = positive_series(state, "deprado_runs_prices")
    bar_size = number(first(state, "deprado_runs_expected_bar_size"))
    buy_probability = number(first(state, "deprado_runs_buy_probability"))
    found = values(state, *KEYS)
    missing = []
    if prices is None:
        missing.append("deprado_runs_prices")
    if bar_size is None:
        missing.append("deprado_runs_expected_bar_size")
    if buy_probability is None:
        missing.append("deprado_runs_buy_probability")
    provenance = first(state, "deprado_runs_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_runs_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if bar_size <= 0 or not 0 <= buy_probability <= 1:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["tick runs inputs require a positive bar size and buy probability in [0, 1]"]
        return result

    expected = bar_size * max(buy_probability, 1 - buy_probability)
    events = run_events(tick_signs(prices), None, expected)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_event_sampling"
    result["deprado_tick_runs_expected"] = expected
    result["deprado_tick_runs_events"] = events
    result["deprado_tick_runs_event_count"] = len(events)
    result["deprado_tick_runs_assessment"] = "TICK_RUN_EVENTS_MEASURED"
    result["warnings"] = ["tick runs bars sample one-sided activity; they do not authorize a trade"]
    return result
