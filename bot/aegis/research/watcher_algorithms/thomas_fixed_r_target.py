"""The 10XROI system's fixed 10R target (and documented 8R exception)."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "thomas_fixed_r_target"
SOURCES = ("LR Thomas — The 10XROI Trading System",)
KEYS = (
    "thomas_stop_pips",
    "thomas_target_pips",
    "thomas_target_multiple",
    "thomas_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "thomas_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("thomas_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    stop = number(first(state, "thomas_stop_pips"))
    target = number(first(state, "thomas_target_pips"))
    multiple = number(first(state, "thomas_target_multiple"))
    if any(value is None or value <= 0 for value in (stop, target, multiple)):
        result["thomas_target_assessment"] = "TARGET_GEOMETRY_INVALID"
        result["reasons"] = ["stop, target, and R multiple must be positive finite observations"]
        return result
    symbol = normalized_status(first(state, "symbol")).replace("/", "")
    is_exception = multiple == 8 and stop == 40 and symbol == "eurusd"
    is_standard = multiple == 10
    if not (is_standard or is_exception) or abs(target - stop * multiple) > 1e-9:
        result["thomas_target_assessment"] = "TARGET_GEOMETRY_INVALID"
        result["reasons"] = ["the source uses a fixed 10R target, with only the documented 40-pip EURUSD 8R exception"]
        return result
    result["thomas_target_assessment"] = "TARGET_GEOMETRY_VALID"
    result["thomas_target_multiple"] = multiple
    result["thomas_target_mode"] = "EURUSD_8R_EXCEPTION" if is_exception else "STANDARD_10R"
    result["reasons"] = ["the fixed target is consistent with the source-defined risk multiple"]
    return result
