"""Inventory-to-zero quote skew perspective from Cartea and Jaimungal."""
from __future__ import annotations

from ._common import absent, base, first, number, normalized_status, values, with_direction

ALGORITHM_ID = "cartea_inventory_skew"
SOURCES = ("Modelling Asset Prices for Algorithmic and High-Frequency Trading",)
KEYS = (
    "cartea_inventory_units",
    "cartea_target_inventory_units",
    "cartea_time_to_flatten_s",
    "cartea_inventory_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "cartea_inventory_data_provenance")):
        missing.append("cartea_inventory_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    inventory = number(first(state, "cartea_inventory_units"))
    target = number(first(state, "cartea_target_inventory_units"))
    time_to_flatten = number(first(state, "cartea_time_to_flatten_s"))
    if None in {inventory, target, time_to_flatten} or time_to_flatten <= 0.0:
        result["reasons"] = ["inventory skew needs finite inventory and a positive remaining flattening horizon"]
        return result
    delta = inventory - target
    result.update({"cartea_inventory_target": target, "cartea_inventory_delta": delta})
    if delta == 0.0:
        result["reasons"] = ["inventory is already at the target and needs no directional flattening skew"]
        return result
    signal = "SELL" if delta > 0.0 else "BUY"
    result["cartea_inventory_rebalance_side"] = signal
    return with_direction(result, state, signal, "inventory skew is directed toward the target of zero exposure")
