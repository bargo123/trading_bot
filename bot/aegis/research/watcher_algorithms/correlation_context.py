"""Cross-asset correlation, beta, and portfolio-context algorithm."""
from __future__ import annotations

from ._common import absent, base, direction, side, strings, values, with_direction

ALGORITHM_ID = "correlation_context"
SOURCES = (
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "Ernest Chan — Quantitative Trading",
    "Andrew Pole — Statistical Arbitrage",
    "Richard Grinold and Ronald Kahn — Active Portfolio Management",
)
KEYS = ("correlation", "correlation_state", "cross_asset", "intermarket", "beta", "hedge_ratio", "basket_direction", "risk_on_off", "dollar_index")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("cross_asset_context",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("divergent", "breakdown", "unstable", "uncorrelated", "contradict")):
        result["view"] = "WAIT"
        result["reasons"] = ["cross-asset context contradicts or does not stably support the snapshot"]
        return result
    signal = direction(text)
    if signal is None and "aligned" in text and side(state):
        signal = side(state)
    if signal:
        return with_direction(result, state, signal, "cross-asset or basket direction is aligned with the snapshot")
    result["view"] = "WAIT"
    result["reasons"] = ["cross-asset context is available without a stable directional relationship"]
    return result
