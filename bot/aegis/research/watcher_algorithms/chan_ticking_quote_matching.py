"""Chan's spread-greater-than-two-ticks ticking/quote-matching perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction


ALGORITHM_ID = "chan_ticking_quote_matching"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_ticking_spread_ticks",
    "chan_ticking_tick_size",
    "chan_ticking_round_trip_commission_per_unit",
    "chan_ticking_price_pressure",
    "chan_ticking_order_priority",
    "chan_ticking_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "chan_ticking_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("chan_ticking_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    spread_ticks = number(first(state, "chan_ticking_spread_ticks"))
    tick_size = number(first(state, "chan_ticking_tick_size"))
    commission = number(first(state, "chan_ticking_round_trip_commission_per_unit"))
    candidate_side = side(state)
    pressure = normalized_status(first(state, "chan_ticking_price_pressure"))
    priority = normalized_status(first(state, "chan_ticking_order_priority"))
    if (
        any(value is None for value in (spread_ticks, tick_size, commission))
        or spread_ticks <= 0
        or tick_size <= 0
        or commission < 0
        or candidate_side is None
    ):
        result["chan_ticking_assessment"] = "INVALID_TICKING_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["observed spread, tick, commission, and candidate side must be valid"]
        return result
    if priority not in {"observed", "measured", "timestamped"}:
        result["chan_ticking_assessment"] = "ORDER_PRIORITY_UNVERIFIED"
        result["view"] = "WAIT"
        result["reasons"] = ["quote matching requires an observed order-priority environment"]
        return result
    if spread_ticks <= 2.0:
        result["chan_ticking_assessment"] = "SPREAD_NOT_GREATER_THAN_TWO_TICKS"
        result["view"] = "WAIT"
        result["reasons"] = ["the source ticking setup requires an original spread greater than two ticks"]
        return result
    expected_side = "buy" if candidate_side == "BUY" else "sell"
    if pressure != expected_side:
        result["chan_ticking_assessment"] = "PRESSURE_DIRECTION_MISMATCH"
        result["view"] = "WAIT"
        result["reasons"] = ["observed price pressure does not agree with the candidate side"]
        return result

    gross_room = (spread_ticks - 2.0) * tick_size
    result["chan_ticking_gross_room"] = gross_room
    if commission >= gross_room:
        result["chan_ticking_assessment"] = "COST_HURDLE_FAILED"
        result["view"] = "WAIT"
        result["reasons"] = ["round-trip commission is not below spread room after the two quote-matching ticks"]
        return result

    result["chan_ticking_assessment"] = "BUY_QUOTE_MATCH" if candidate_side == "BUY" else "SELL_QUOTE_MATCH"
    return with_direction(
        result,
        state,
        candidate_side,
        "observed pressure and execution geometry support the source ticking/quote-matching hypothesis",
    )
