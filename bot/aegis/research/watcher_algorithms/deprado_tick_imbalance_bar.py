"""López de Prado tick-imbalance-bar event diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import finite_series, provenance_ok

ALGORITHM_ID = "deprado_tick_imbalance_bar"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_tick_prices",
    "deprado_tick_expected_bar_size",
    "deprado_tick_buy_probability",
    "deprado_tick_imbalance_data_provenance",
)


def evaluate(state):
    prices = finite_series(state, "deprado_tick_prices")
    expected_bar_size = number(first(state, "deprado_tick_expected_bar_size"))
    buy_probability = number(first(state, "deprado_tick_buy_probability"))
    found = values(state, *KEYS)
    missing = []
    if prices is None or len(prices) < 2:
        missing.append("deprado_tick_prices")
    if expected_bar_size is None:
        missing.append("deprado_tick_expected_bar_size")
    if buy_probability is None:
        missing.append("deprado_tick_buy_probability")
    provenance = first(state, "deprado_tick_imbalance_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_tick_imbalance_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if expected_bar_size <= 0 or not 0.0 <= buy_probability <= 1.0:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["tick imbalance requires a positive expected bar size and buy probability in [0, 1]"]
        return result

    signs = [0]
    previous_sign = 0
    for before, after in zip(prices, prices[1:]):
        if after > before:
            previous_sign = 1
        elif after < before:
            previous_sign = -1
        signs.append(previous_sign)

    expected_imbalance = expected_bar_size * abs(2.0 * buy_probability - 1.0)
    imbalance = 0.0
    bar_start = 0
    events = []
    for index, sign in enumerate(signs):
        imbalance += sign
        if abs(imbalance) > expected_imbalance:
            events.append({
                "start_index": bar_start,
                "end_index": index,
                "direction": "UP" if imbalance > 0 else "DOWN",
                "signed_imbalance": imbalance,
            })
            imbalance = 0.0
            bar_start = index + 1

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_event_sampling"
    result["deprado_tick_signs"] = signs
    result["deprado_tick_expected_imbalance"] = expected_imbalance
    result["deprado_tick_bar_events"] = events
    result["deprado_tick_event_count"] = len(events)
    result["deprado_tick_imbalance_assessment"] = "TICK_IMBALANCE_EVENTS_MEASURED"
    result["warnings"] = ["tick-imbalance bars are a sampling diagnostic, not a trade direction"]
    return result
