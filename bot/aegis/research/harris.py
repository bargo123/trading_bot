"""Harris supplies microstructure/cost constraints, not a one-bar signal."""
from __future__ import annotations


def spread_allows_take(*, spread_pips: float, take_pips: float) -> bool:
    if take_pips <= 0:
        return False
    return float(spread_pips) < float(take_pips)


def jump_is_local_heuristic() -> bool:
    """`harris_jump` in live YAML is a local ATR jump heuristic, not Harris's book method."""
    return True
