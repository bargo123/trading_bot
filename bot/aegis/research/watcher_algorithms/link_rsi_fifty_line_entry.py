"""Marcel Link's RSI 50-line cross/stall entry perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "link_rsi_fifty_line_entry"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_rsi_current",
    "link_rsi_previous",
    "link_rsi_fifty_line",
    "link_rsi_stall_confirmed",
    "link_rsi_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_rsi_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_rsi_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    current = number(first(state, "link_rsi_current"))
    previous = number(first(state, "link_rsi_previous"))
    fifty = number(first(state, "link_rsi_fifty_line"))
    stall = first(state, "link_rsi_stall_confirmed")
    if (
        any(value is None for value in (current, previous, fifty))
        or not 0.0 <= current <= 100.0
        or not 0.0 <= previous <= 100.0
        or not 0.0 < fifty < 100.0
        or not isinstance(stall, bool)
    ):
        result["link_rsi_action"] = "INVALID_RSI_INPUT"
        result["reasons"] = ["RSI observations must be bounded and the 50-line stall must be explicit"]
        return result

    cross_up = previous <= fifty < current
    cross_down = previous >= fifty > current
    near_fifty = abs(current - fifty) <= 2.0
    result.update(
        {
            "link_rsi_fifty_cross": "UP" if cross_up else "DOWN" if cross_down else "NONE",
            "link_rsi_near_fifty": near_fifty,
            "directional_claim": True,
        }
    )
    if candidate_side == "BUY" and cross_up:
        return with_direction(
            {**result, "link_rsi_action": "BUY_RSI_50_CROSS"},
            state,
            "BUY",
            "RSI crossed above the source equilibrium line",
        )
    if candidate_side == "SELL" and cross_down:
        return with_direction(
            {**result, "link_rsi_action": "SELL_RSI_50_CROSS"},
            state,
            "SELL",
            "RSI crossed below the source equilibrium line",
        )
    if candidate_side == "BUY" and current > fifty and current >= previous:
        return with_direction(
            {**result, "link_rsi_action": "BUY_RSI_ABOVE_50"},
            state,
            "BUY",
            "RSI is observed above the source 50-line with non-decreasing support",
        )
    if candidate_side == "SELL" and current < fifty and current <= previous:
        return with_direction(
            {**result, "link_rsi_action": "SELL_RSI_BELOW_50"},
            state,
            "SELL",
            "RSI is observed below the source 50-line with non-increasing resistance",
        )
    if candidate_side == "BUY" and stall and near_fifty:
        return with_direction(
            {**result, "link_rsi_action": "BUY_RSI_50_STALL"},
            state,
            "BUY",
            "RSI held near the source 50-line support during a strong-market pullback",
        )
    if candidate_side == "SELL" and stall and near_fifty:
        return with_direction(
            {**result, "link_rsi_action": "SELL_RSI_50_STALL"},
            state,
            "SELL",
            "RSI held near the source 50-line resistance during a strong-market pullback",
        )
    result["link_rsi_action"] = "NO_RSI_50_SIGNAL"
    result["reasons"] = ["RSI did not produce a fresh 50-line cross or an explicitly confirmed stall"]
    return result
