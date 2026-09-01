"""Chan's pro-rata bid/ask imbalance ratio-trade perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction


ALGORITHM_ID = "chan_ratio_trade"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_ratio_bid_size",
    "chan_ratio_ask_size",
    "chan_ratio_imbalance_min",
    "chan_ratio_spread_ticks",
    "chan_ratio_tick_size",
    "chan_ratio_round_trip_commission_per_unit",
    "chan_ratio_fill_model",
    "chan_ratio_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "chan_ratio_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("chan_ratio_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    bid_size = number(first(state, "chan_ratio_bid_size"))
    ask_size = number(first(state, "chan_ratio_ask_size"))
    minimum = number(first(state, "chan_ratio_imbalance_min"))
    spread_ticks = number(first(state, "chan_ratio_spread_ticks"))
    tick_size = number(first(state, "chan_ratio_tick_size"))
    commission = number(first(state, "chan_ratio_round_trip_commission_per_unit"))
    candidate_side = side(state)
    if (
        any(value is None for value in (bid_size, ask_size, minimum, spread_ticks, tick_size, commission))
        or bid_size <= 0
        or ask_size <= 0
        or minimum <= 1.0
        or spread_ticks <= 0
        or tick_size <= 0
        or commission < 0
        or candidate_side is None
    ):
        result["chan_ratio_assessment"] = "INVALID_RATIO_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["observed queue sizes, imbalance threshold, tick, spread, commission, and side must be valid"]
        return result

    fill_model = normalized_status(first(state, "chan_ratio_fill_model"))
    if fill_model != "pro rata":
        result["chan_ratio_assessment"] = "NON_PRORATA_FILL_MODEL"
        result["view"] = "WAIT"
        result["reasons"] = ["the source ratio trade assumes a pro-rata fill model"]
        return result

    ratio = bid_size / ask_size if candidate_side == "BUY" else ask_size / bid_size
    result["chan_ratio"] = ratio
    result["chan_ratio_gross_room"] = spread_ticks * tick_size
    if ratio < minimum:
        result["chan_ratio_assessment"] = "INSUFFICIENT_IMBALANCE"
        result["view"] = "WAIT"
        result["reasons"] = ["the pressure-side queue is not sufficiently larger than the opposing queue"]
        return result
    if commission >= result["chan_ratio_gross_room"]:
        result["chan_ratio_assessment"] = "COST_HURDLE_FAILED"
        result["view"] = "WAIT"
        result["reasons"] = ["round-trip commission is not below the observed spread room"]
        return result

    result["chan_ratio_assessment"] = (
        "BUY_PRESSURE_RATIO_TRADE" if candidate_side == "BUY" else "SELL_PRESSURE_RATIO_TRADE"
    )
    return with_direction(
        result,
        state,
        candidate_side,
        "observed pro-rata queue imbalance and positive spread room support the ratio-trade hypothesis",
    )
