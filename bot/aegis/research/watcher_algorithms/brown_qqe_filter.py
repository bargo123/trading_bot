"""Brown's QMP-trigger plus QQE midline/extreme filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "brown_qqe_filter"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_qmp_dot",
    "brown_qqe_line_1",
    "brown_qqe_line_2",
    "brown_qqe_mode",
    "brown_qqe_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "qmp" in label and "qqe" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_qqe_data_provenance")):
        missing.append("brown_qqe_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    dot = normalized_status(first(state, "brown_qmp_dot"))
    line_1 = number(first(state, "brown_qqe_line_1"))
    line_2 = number(first(state, "brown_qqe_line_2"))
    mode = normalized_status(first(state, "brown_qqe_mode"))
    if dot not in {"green", "red"} or None in {line_1, line_2} or not 0 <= line_1 <= 100 or not 0 <= line_2 <= 100 or mode not in {"midline", "extreme"}:
        result["brown_qqe_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["QMP dot, two bounded QQE lines, and midline/extreme mode are required"]
        return result
    if mode == "midline":
        if dot == "green" and line_1 < 50 and line_2 < 50:
            result["brown_qqe_assessment"] = "MIDLINE_BUY_FILTER"
            return with_direction(result, state, "BUY", "both observed QQE lines are below 50 with a green QMP trigger")
        if dot == "red" and line_1 > 50 and line_2 > 50:
            result["brown_qqe_assessment"] = "MIDLINE_SELL_FILTER"
            return with_direction(result, state, "SELL", "both observed QQE lines are above 50 with a red QMP trigger")
        result["brown_qqe_assessment"] = "MIDLINE_FILTER_NOT_CLEARED"
        result["reasons"] = ["both QQE lines must be on the QMP-consistent side of 50"]
        return result
    if dot == "green" and min(line_1, line_2) <= 35:
        result["brown_qqe_assessment"] = "OVERSOLD_BUY_FILTER"
        return with_direction(result, state, "BUY", "an observed QQE line touched or crossed 35 with a green QMP trigger")
    if dot == "red" and max(line_1, line_2) >= 65:
        result["brown_qqe_assessment"] = "OVERBOUGHT_SELL_FILTER"
        return with_direction(result, state, "SELL", "an observed QQE line touched or crossed 65 with a red QMP trigger")
    result["brown_qqe_assessment"] = "EXTREME_FILTER_NOT_CLEARED"
    result["reasons"] = ["the QQE lines do not reach the selected 35/65 extreme for the QMP direction"]
    return result
