"""Chan's bulk-volume-classification order-flow perspective (Machine Trading, ch. 6)."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "chan_bulk_volume_order_flow"
SOURCES = ("Ernest P. Chan — Machine Trading",)
KEYS = (
    "side",
    "chan_bvc_delta_price",
    "chan_bvc_delta_price_sigma",
    "chan_bvc_volume",
    "chan_bvc_entry_fraction",
    "chan_bvc_exit_fraction",
    "chan_bvc_position",
    "chan_bvc_data_provenance",
)


def _position(value):
    normalized = normalized_status(value).replace(" ", "_")
    return normalized if normalized in {"flat", "long", "short"} else None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "chan_bvc_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("chan_bvc_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    candidate_side = side(state)
    delta = number(first(state, "chan_bvc_delta_price"))
    sigma = number(first(state, "chan_bvc_delta_price_sigma"))
    volume = number(first(state, "chan_bvc_volume"))
    entry_fraction = number(first(state, "chan_bvc_entry_fraction"))
    exit_fraction = number(first(state, "chan_bvc_exit_fraction"))
    position = _position(first(state, "chan_bvc_position"))
    if (
        candidate_side not in {"BUY", "SELL"}
        or delta is None
        or sigma is None
        or volume is None
        or entry_fraction is None
        or exit_fraction is None
        or position is None
        or sigma <= 0.0
        or volume <= 0.0
        or not 0.5 < entry_fraction <= 1.0
        or not 0.0 <= exit_fraction <= 0.5
    ):
        result["chan_bvc_action"] = "INVALID_BVC_INPUT"
        result["reasons"] = [
            "BVC needs a side, finite nonzero price-change scale and volume, flat/long/short position, and bounded thresholds"
        ]
        return result

    z_score = delta / sigma
    buy_fraction = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
    sell_fraction = 1.0 - buy_fraction
    result.update({
        "chan_bvc_z_score": z_score,
        "chan_bvc_buy_fraction": buy_fraction,
        "chan_bvc_sell_fraction": sell_fraction,
        "chan_bvc_net_order_flow": volume * (2.0 * buy_fraction - 1.0),
        "chan_bvc_position": position,
        "directional_claim": position == "flat",
    })

    if position == "long":
        if buy_fraction < exit_fraction:
            result["chan_bvc_action"] = "EXIT_LONG"
            result["reasons"] = ["observed BVC buy fraction fell below the explicit long-position exit threshold"]
        else:
            result["chan_bvc_action"] = "HOLD_LONG"
            result["reasons"] = ["observed BVC buy fraction remains above the explicit long-position exit threshold"]
        return result
    if position == "short":
        if buy_fraction > 1.0 - exit_fraction:
            result["chan_bvc_action"] = "EXIT_SHORT"
            result["reasons"] = ["observed BVC buy fraction reached the explicit short-position exit threshold"]
        else:
            result["chan_bvc_action"] = "HOLD_SHORT"
            result["reasons"] = ["observed BVC buy fraction remains below the explicit short-position exit threshold"]
        return result

    result["directional_claim"] = True
    if buy_fraction >= entry_fraction and candidate_side == "BUY":
        result["chan_bvc_action"] = "BUY_ENTRY"
        return with_direction(result, state, "BUY", "observed BVC buy fraction cleared the explicit entry threshold")
    if sell_fraction >= entry_fraction and candidate_side == "SELL":
        result["chan_bvc_action"] = "SELL_ENTRY"
        return with_direction(result, state, "observed BVC sell fraction cleared the explicit entry threshold")
    result["chan_bvc_action"] = "NO_ENTRY"
    result["reasons"] = ["neither observed BVC side cleared the explicit entry threshold for the candidate side"]
    return result
