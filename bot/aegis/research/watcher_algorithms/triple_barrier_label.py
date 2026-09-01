"""Triple-barrier labeling specification, without peeking at future outcomes."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values

ALGORITHM_ID = "triple_barrier_label"
SOURCES = (
    "Marcos López de Prado — Advances in Financial Machine Learning",
    "Stefan Jansen — Machine Learning for Algorithmic Trading",
)
KEYS = ("label_entry_price", "upper_barrier", "lower_barrier", "label_horizon_s", "label_policy")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("point_in_time_triple_barrier_specification",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    entry = number(first(state, "label_entry_price"))
    upper = number(first(state, "upper_barrier"))
    lower = number(first(state, "lower_barrier"))
    horizon = number(first(state, "label_horizon_s"))
    policy = strings(state, "label_policy")
    if "triple" not in policy or None in {entry, upper, lower, horizon}:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_triple_barrier_specification"]
        return result
    if not (lower < entry < upper and horizon > 0):
        result["view"] = "WAIT"
        result["reasons"] = ["triple-barrier geometry or horizon is invalid"]
        return result
    result["labeling_ready"] = True
    result["outcome"] = "UNOBSERVED"
    result["reasons"] = ["barriers are defined point-in-time; future quotes are intentionally not inspected here"]
    result["view"] = "WAIT"
    return result
