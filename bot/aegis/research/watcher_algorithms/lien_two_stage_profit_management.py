"""Kathy Lien's one-R scale-out and trailing-stop management study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values


ALGORITHM_ID = "lien_two_stage_profit_management"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "side",
    "lien_mgmt_entry_price",
    "lien_mgmt_current_price",
    "lien_mgmt_pip_size",
    "lien_mgmt_initial_risk_pips",
    "lien_mgmt_trailing_distance_pips",
    "lien_mgmt_partial_closed",
    "lien_mgmt_breakeven_stop_active",
    "lien_mgmt_parabolic_sar",
    "lien_mgmt_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "lien_mgmt_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("lien_mgmt_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    candidate_side = side(state)
    entry = number(first(state, "lien_mgmt_entry_price"))
    current = number(first(state, "lien_mgmt_current_price"))
    pip_size = number(first(state, "lien_mgmt_pip_size"))
    initial_risk = number(first(state, "lien_mgmt_initial_risk_pips"))
    trailing_distance = number(first(state, "lien_mgmt_trailing_distance_pips"))
    sar = number(first(state, "lien_mgmt_parabolic_sar"))
    partial_closed = first(state, "lien_mgmt_partial_closed")
    breakeven_active = first(state, "lien_mgmt_breakeven_stop_active")
    if (
        any(value is None for value in (entry, current, pip_size, initial_risk, trailing_distance, sar))
        or entry <= 0
        or current <= 0
        or pip_size <= 0
        or initial_risk <= 0
        or trailing_distance <= 0
        or sar <= 0
        or not isinstance(partial_closed, bool)
        or not isinstance(breakeven_active, bool)
    ):
        result["lien_mgmt_action"] = "INVALID_MANAGEMENT_INPUT"
        result["reasons"] = ["management needs positive prices/distances and explicit partial/breakeven state"]
        return result
    if partial_closed and not breakeven_active:
        result["lien_mgmt_action"] = "INVALID_MANAGEMENT_STATE"
        result["reasons"] = ["a scaled-out remainder must have its stop moved to entry before trailing"]
        return result

    current_profit_pips = (
        (current - entry) / pip_size if candidate_side == "BUY" else (entry - current) / pip_size
    )
    initial_stop = entry - initial_risk * pip_size if candidate_side == "BUY" else entry + initial_risk * pip_size
    trailing_stop = current - trailing_distance * pip_size if candidate_side == "BUY" else current + trailing_distance * pip_size
    sar_is_protective = sar > entry if candidate_side == "BUY" else sar < entry
    result.update(
        {
            "lien_mgmt_current_profit_pips": current_profit_pips,
            "lien_mgmt_initial_stop_price": initial_stop,
            "lien_mgmt_trailing_stop_price": trailing_stop,
            "lien_mgmt_scale_trigger_pips": initial_risk,
            "lien_mgmt_parabolic_sar_is_protective": sar_is_protective,
            "directional_claim": False,
        }
    )
    if current_profit_pips < initial_risk:
        result["lien_mgmt_action"] = "HOLD_INITIAL_STOP"
        result["lien_mgmt_proposed_stop_price"] = initial_stop
        result["reasons"] = ["profit has not yet reached the initial risk amount required for the source scale-out"]
        return result
    if not partial_closed:
        result["lien_mgmt_action"] = "SCALE_HALF_MOVE_TO_BREAKEVEN"
        result["lien_mgmt_proposed_stop_price"] = entry
        result["reasons"] = ["profit reached the initial risk amount: close half, move the stop to entry, and trail the remainder"]
        return result
    if sar_is_protective:
        result["lien_mgmt_action"] = "USE_PARABOLIC_SAR_STOP"
        result["lien_mgmt_proposed_stop_price"] = sar
        result["reasons"] = ["after scale-out, the observed Parabolic SAR has moved beyond entry in the protective direction"]
    else:
        result["lien_mgmt_action"] = "TRAIL_REMAINDER"
        result["lien_mgmt_proposed_stop_price"] = trailing_stop
        result["reasons"] = ["after scale-out, trail the remaining position by the source distance"]
    return result
