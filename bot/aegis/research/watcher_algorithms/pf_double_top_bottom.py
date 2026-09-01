"""Jeremy du Plessis' basic three-box Point-and-Figure signal."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_double_top_bottom"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 115-123"
KEYS = (
    "pf_box_reversal",
    "pf_pattern_type",
    "pf_pattern_structure",
    "pf_breakout_direction",
    "pf_pattern_columns",
    "pf_breakout_confirmed",
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
    if normalized_status(first(state, "pf_box_reversal")) != "3 box":
        result["view"] = "WAIT"
        result["reasons"] = ["the basic double-top/bottom signal is evaluated on a three-box chart"]
        return result
    pattern = normalized_status(first(state, "pf_pattern_type"))
    structure = normalized_status(first(state, "pf_pattern_structure"))
    if pattern not in {"double top", "double bottom"} or structure not in {"continuation", "reversal"}:
        result["view"] = "WAIT"
        result["reasons"] = ["double-top/bottom and continuation/reversal structure must be explicit"]
        return result
    columns = number(first(state, "pf_pattern_columns"))
    minimum_columns = 4 if structure == "reversal" else 3
    if columns is None or columns < minimum_columns or columns != int(columns):
        result["view"] = "WAIT"
        result["reasons"] = [f"a {structure} double-top/bottom needs at least {minimum_columns} observed columns"]
        return result
    if not _truthy(first(state, "pf_breakout_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the double-top/bottom breakout is not confirmed"]
        return result
    direction = normalized_status(first(state, "pf_breakout_direction"))
    if pattern == "double top" and direction == "up":
        signal = "BUY"
    elif pattern == "double bottom" and direction == "down":
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["double-top/bottom type and breakout direction do not agree"]
        return result
    result["pf_double_signal_structure"] = structure
    result["pf_double_signal_columns"] = int(columns)
    return with_direction(result, state, signal, "confirmed Point-and-Figure double-top/bottom breakout")
