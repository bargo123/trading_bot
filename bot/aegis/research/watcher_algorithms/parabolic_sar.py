"""Parabolic-SAR trend/flip perspective on observed quote prices."""
from __future__ import annotations

from ._common import base, first, number, text, values, with_direction

ALGORITHM_ID = "parabolic_sar"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "The New Trading for a Living — Alexander Elder",
)
KEYS = ("parabolic_sar", "sar", "sar_state", "sar_direction", "sar_flip", "sar_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("parabolic_sar",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = text(first(state, "sar_state", "sar_direction", "sar_flip")).lower()
    if any(token in state_text for token in ("bear", "down", "flip_down")):
        return with_direction(result, state, "SELL", "Parabolic SAR is below-to-above price or flipped down")
    if any(token in state_text for token in ("bull", "up", "flip_up")):
        return with_direction(result, state, "BUY", "Parabolic SAR is below price or flipped up")
    sar = number(first(state, "parabolic_sar", "sar"))
    price = number(first(state, "mid", "current_price", "entry"))
    if sar is not None and price is not None and price != sar:
        return with_direction(result, state, "BUY" if price > sar else "SELL", "price is positioned relative to the recorded SAR")
    result["view"] = "WAIT"
    result["reasons"] = ["SAR is present without a resolvable trend or price relation"]
    return result
