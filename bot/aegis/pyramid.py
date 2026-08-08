from __future__ import annotations

from typing import Sequence


def next_pyramid_sl(side: str, entries: Sequence[float], new_entry: float) -> float:
    """
    Fuller smart pyramid: on each add, trail unified stop to the prior entry
    so aggregate risk stays ≈ original 1R (first leg → BE, later legs lock profit).
    `entries` = existing leg entries before the new add; `new_entry` unused for SL level
    but kept for call-site clarity.
    """
    _ = new_entry
    if not entries:
        raise ValueError("pyramid requires at least one existing entry")
    return float(entries[-1])


def should_pyramid(
    *,
    side: str,
    entry: float,
    price: float,
    initial_risk: float,
    adds: int,
    max_adds: int,
    add_r: float,
    adx: float,
    adx_min: float,
    enabled: bool,
) -> bool:
    if not enabled:
        return False
    if initial_risk <= 0 or adds >= max_adds:
        return False
    if adx < adx_min:
        return False
    # Need +add_r * (adds+1) R of open profit vs initial entry before next add
    need = initial_risk * float(add_r) * float(adds + 1)
    if side == "buy":
        move = price - entry
    else:
        move = entry - price
    return move >= need
