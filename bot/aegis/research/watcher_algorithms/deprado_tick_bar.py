"""López de Prado standard tick-bar construction diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_bars_common import positive_series, standard_bars
from ._deprado_common import provenance_ok

ALGORITHM_ID = "deprado_tick_bar"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = ("deprado_standard_prices", "deprado_tick_bar_size", "deprado_standard_bar_data_provenance")


def evaluate(state):
    prices = positive_series(state, "deprado_standard_prices")
    bar_size = number(first(state, "deprado_tick_bar_size"))
    found = values(state, *KEYS)
    missing = []
    if prices is None:
        missing.append("deprado_standard_prices")
    if bar_size is None:
        missing.append("deprado_tick_bar_size")
    provenance = first(state, "deprado_standard_bar_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_standard_bar_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if not bar_size.is_integer() or bar_size <= 0:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["tick-bar size must be a positive integer"]
        return result

    bars = standard_bars(prices, [1.0] * len(prices), bar_size)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_bar_construction"
    result["deprado_standard_bars"] = bars
    result["deprado_standard_bar_count"] = len(bars)
    result["deprado_standard_bar_assessment"] = "TICK_BARS_MEASURED"
    result["warnings"] = ["tick bars structure observations; they do not authorize a trade"]
    return result
