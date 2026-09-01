"""Grinold-Kahn forecast-quality context, never a directional signal by itself."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "fundamental_law"
SOURCES = ("Richard Grinold and Ronald Kahn — Active Portfolio Management",)
KEYS = ("signal_breadth", "information_coefficient", "transfer_coefficient", "fundamental_law_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_ic_breadth_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    breadth = number(first(state, "signal_breadth"))
    ic = number(first(state, "information_coefficient"))
    tc = number(first(state, "transfer_coefficient"))
    status = first(state, "fundamental_law_status")
    if None in {breadth, ic, tc} or breadth <= 0 or not 0 <= tc <= 1 or not explicitly_validated(status):
        result["view"] = "WAIT"
        result["reasons"] = ["forecast quality context is incomplete or unvalidated"]
        return result
    result["forecast_quality_score"] = ic * (breadth ** 0.5) * tc
    result["view"] = "WAIT"
    result["reasons"] = ["information coefficient and breadth describe forecast quality, not trade direction"]
    return result
