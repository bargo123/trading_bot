"""Davey's three-close baseline and capped ATR stop, as research only."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values, with_direction


ALGORITHM_ID = "davey_three_bar_baseline"
SOURCES = ("Kevin J. Davey — Building Winning Algorithmic Trading Systems",)
KEYS = (
    "davey_baseline_close_history",
    "davey_baseline_true_range_history",
    "davey_baseline_atr_multiplier",
    "davey_baseline_big_point_value",
    "davey_baseline_stop_cap",
    "davey_baseline_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if result and all(item is not None for item in result) else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "davey_baseline_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("davey_baseline_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    closes = _series(first(state, "davey_baseline_close_history"))
    true_ranges = _series(first(state, "davey_baseline_true_range_history"))
    atr_multiplier = number(first(state, "davey_baseline_atr_multiplier"))
    big_point_value = number(first(state, "davey_baseline_big_point_value"))
    stop_cap = number(first(state, "davey_baseline_stop_cap"))
    if (
        closes is None
        or len(closes) < 3
        or true_ranges is None
        or len(true_ranges) < 14
        or any(item <= 0 for item in true_ranges[-14:])
        or atr_multiplier is None
        or atr_multiplier <= 0
        or big_point_value is None
        or big_point_value <= 0
        or stop_cap is None
        or stop_cap <= 0
    ):
        result["davey_baseline_action"] = "INVALID_BASELINE_PARAMETERS"
        result["reasons"] = ["the baseline requires three closes and a positive 14-period true-range stop input"]
        return result

    atr14 = sum(true_ranges[-14:]) / 14.0
    stop_loss = min(atr_multiplier * big_point_value * atr14, stop_cap)
    result.update(
        {
            "davey_baseline_atr14": atr14,
            "davey_baseline_stop_loss": stop_loss,
            "davey_baseline_stop_formula": "min(atr_multiplier * big_point_value * ATR14, stop_cap)",
            "directional_claim": True,
        }
    )
    if closes[-1] < closes[-2] < closes[-3]:
        result["davey_baseline_action"] = "BUY_NEXT_BAR"
        return with_direction(result, state, "BUY", "three consecutive lower closes triggered the baseline long entry")
    if closes[-1] > closes[-2] > closes[-3]:
        result["davey_baseline_action"] = "SELL_SHORT_NEXT_BAR"
        return with_direction(result, state, "SELL", "three consecutive higher closes triggered the baseline short entry")
    result["davey_baseline_action"] = "NO_THREE_BAR_TRIGGER"
    result["reasons"] = ["the latest three closes were not strictly ordered in either direction"]
    return result
