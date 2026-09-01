"""Jeremy du Plessis' opposing-poles confirmation perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "pf_opposing_poles"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 163-164"
KEYS = (
    "pf_first_pole_type",
    "pf_second_pole_type",
    "pf_opposing_poles_confirmed",
    "pf_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pf_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not _truthy(first(state, "pf_opposing_poles_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the second pole is not confirmed after the first"]
        return result
    first_pole = normalized_status(first(state, "pf_first_pole_type"))
    second_pole = normalized_status(first(state, "pf_second_pole_type"))
    if first_pole == "high" and second_pole == "low":
        result["pf_opposing_poles_assessment"] = "CONFIRMED"
        return with_direction(result, state, "BUY", "a low pole following a high pole strengthens the bullish reversal")
    if first_pole == "low" and second_pole == "high":
        result["pf_opposing_poles_assessment"] = "CONFIRMED"
        return with_direction(result, state, "SELL", "a high pole following a low pole strengthens the bearish reversal")
    result["view"] = "WAIT"
    result["reasons"] = ["the two observed poles are not opposing"]
    return result
