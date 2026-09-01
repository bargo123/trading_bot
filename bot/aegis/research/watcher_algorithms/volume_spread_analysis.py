"""Volume-spread-analysis perspective using an explicitly annotated bar pattern."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, number, strings, values, with_direction

ALGORITHM_ID = "volume_spread_analysis"
SOURCES = ("Anna Coulling — A Complete Guide to Volume Price Analysis",)
KEYS = ("vsa_pattern", "vsa_confirmation", "vsa_volume_ratio", "vsa_bar_spread", "vsa_data_provenance")

_BUY = {"no_supply", "stopping_volume", "selling_climax", "effort_result_up"}
_SELL = {"no_demand", "upthrust", "buying_climax", "effort_result_down"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("annotated_vsa_pattern",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = str(first(state, "vsa_pattern") or "").strip().lower().replace(" ", "_")
    confirmation = strings(state, "vsa_confirmation")
    volume = number(first(state, "vsa_volume_ratio"))
    bar_spread = number(first(state, "vsa_bar_spread", "bar_range"))
    if pattern not in _BUY | _SELL or not explicitly_confirmed(confirmation):
        result["view"] = "WAIT"
        result["reasons"] = ["VSA requires a named pattern with explicit confirmation"]
        return result
    if volume is None or volume <= 0 or bar_spread is None or bar_spread <= 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["positive_volume_and_bar_spread"]
        return result
    provenance = strings(state, "vsa_data_provenance", "volume_data_provenance")
    if not explicitly_observed(provenance, accepted=("real", "volume", "traded")):
        result["warnings"] = ["VSA requires real traded-volume provenance"]
        result["view"] = "WAIT"
        result["reasons"] = ["VSA volume is absent or a declared proxy"]
        return result
    signal = "BUY" if pattern in _BUY else "SELL"
    return with_direction(result, state, signal, f"confirmed VSA pattern: {pattern}")
