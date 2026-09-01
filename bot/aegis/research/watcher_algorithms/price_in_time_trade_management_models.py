"""The Price-in-Time source's three explicit trade-management models."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "price_in_time_trade_management_models"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "side",
    "pit_management_model",
    "pit_tp_stage",
    "pit_management_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    model = normalized_status(first(state, "pit_management_model"))
    stage = number(first(state, "pit_tp_stage"))
    missing = [
        key
        for key, value in (
            ("side", first(state, "side")),
            ("pit_management_model", model),
            ("pit_tp_stage", stage),
        )
        if value is None or value == ""
    ]
    provenance = first(state, "pit_management_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        missing.append("pit_management_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if stage < 1.0 or stage != int(stage):
        result["reasons"] = ["TP stage must be a positive integer recognized by the selected source management model"]
        return result
    actions = {
        "model 1": {1.0: "MOVE_STOP_TO_BREAKEVEN", 2.0: "MOVE_STOP_TO_TP1", 3.0: "MOVE_STOP_TO_TP2", 4.0: "MOVE_STOP_TO_TP3"},
        "model 2": {1.0: "CLOSE_HALF_KEEP_STOP", 2.0: "MOVE_STOP_TO_TP1", 3.0: "CLOSE_REMAINDER_AT_TP3"},
        "model 3": {1.0: "MOVE_STOP_TO_BREAKEVEN", 2.0: "CLOSE_ALL_AT_TP2"},
    }
    action = actions.get(model, {}).get(stage)
    if model == "model 1" and action is None:
        action = f"MOVE_STOP_TO_TP{int(stage) - 1}"
    if action is None:
        result["reasons"] = ["the selected management model has no action at this TP stage"]
        return result
    result["pit_management_action"] = action
    result["pit_management_model"] = model.upper().replace(" ", "_")
    result["pit_management_stage"] = int(stage)
    result["reasons"] = ["the observed TP stage maps to the selected source management model"]
    return result
