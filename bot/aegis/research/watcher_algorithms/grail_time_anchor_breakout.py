"""The Holy Grail book's explicit 08:00 UK price-anchor study.

This is a read-only research perspective.  The fixed bracket values are
reported as source parameters, not as a production order instruction.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "grail_time_anchor_breakout"
SOURCES = ("James Windsor — The Holy Grail Forex Trading System",)
KEYS = (
    "grail_reference_pair",
    "grail_anchor_time",
    "grail_anchor_price",
    "grail_current_price",
    "grail_pip_size",
    "grail_breakout_distance_pips",
    "grail_stop_pips",
    "grail_target_pips",
    "grail_trailing_stop_pips",
    "grail_rule_version",
    "grail_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "grail_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("grail_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if str(first(state, "grail_reference_pair") or "").upper() != "GBPUSD":
        result["view"] = "WAIT"
        result["reasons"] = ["the appendix rule is specified for GBPUSD only"]
        return result
    if normalized_status(first(state, "grail_anchor_time")) != "08:00 uk":
        result["view"] = "WAIT"
        result["reasons"] = ["the 08:00 UK anchor was not observed"]
        return result
    parameters = (
        ("grail_breakout_distance_pips", 40.0),
        ("grail_stop_pips", 80.0),
        ("grail_target_pips", 240.0),
        ("grail_trailing_stop_pips", 60.0),
    )
    for key, expected in parameters:
        value = number(first(state, key))
        if value is None or value != expected:
            result["view"] = "WAIT"
            result["reasons"] = [f"baseline appendix parameter {key} is not exactly {expected:g} pips"]
            return result
    if normalized_status(first(state, "grail_rule_version")) != "appendix baseline":
        result["view"] = "WAIT"
        result["reasons"] = ["a non-baseline Grail variant is not treated as the source rule"]
        return result
    anchor = number(first(state, "grail_anchor_price"))
    current = number(first(state, "grail_current_price"))
    pip = number(first(state, "grail_pip_size"))
    if anchor is None or current is None or pip is None or anchor <= 0 or current <= 0 or pip <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["anchor, current price, and pip size must be valid positive observations"]
        return result
    distance = (current - anchor) / pip
    threshold = 40.0
    signal = "BUY" if distance >= threshold else "SELL" if distance <= -threshold else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["price has not reached either 40-pip anchor trigger"]
        return result
    result["grail_distance_from_anchor_pips"] = distance
    result["grail_source_geometry"] = {"stop_pips": 80.0, "target_pips": 240.0, "trailing_stop_pips": 60.0}
    return with_direction(result, state, signal, "the causal GBPUSD price is beyond the source's 08:00 UK anchor trigger")
