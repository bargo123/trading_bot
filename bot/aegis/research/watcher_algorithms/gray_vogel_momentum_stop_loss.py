"""Gray--Vogel momentum stop-loss study, represented as risk management only."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values


ALGORITHM_ID = "gray_vogel_momentum_stop_loss"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_stop_loss_position_return",
    "gray_stop_loss_threshold",
    "gray_stop_loss_monitoring_frequency",
    "gray_stop_loss_rebalance_state",
    "gray_stop_loss_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable")) and any(
        token in label for token in ("observed", "measured", "historical")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_stop_loss_data_provenance")):
        missing.append("gray_stop_loss_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    candidate_side = side(state)
    position_return = number(first(state, "gray_stop_loss_position_return"))
    threshold = number(first(state, "gray_stop_loss_threshold"))
    frequency = normalized_status(first(state, "gray_stop_loss_monitoring_frequency"))
    rebalance = normalized_status(first(state, "gray_stop_loss_rebalance_state"))
    if candidate_side not in {"BUY", "SELL"} or position_return is None or threshold is None or threshold <= 0.0 or frequency != "daily" or rebalance != "monthly":
        result["gray_stop_loss_action"] = "INVALID_STOP_LOSS_INPUT"
        result["reasons"] = ["the study requires a side, finite position return, positive threshold, daily monitoring, and monthly rebalance state"]
        return result
    triggered = position_return <= -threshold if candidate_side == "BUY" else position_return >= threshold
    result["gray_stop_loss_action"] = "STOP_LOSS_TRIGGERED" if triggered else "WITHIN_STOP"
    result["reasons"] = [
        "the observed position return breached the source stop-loss threshold and would leave the portfolio in cash"
        if triggered
        else "the observed position return remains within the source stop-loss threshold"
    ]
    return result
