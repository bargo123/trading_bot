"""Brown's exact 50/100/240 moving-average and QMP alignment perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "brown_multi_ma_alignment"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_qmp_dot",
    "brown_ma_50",
    "brown_ma_100",
    "brown_ma_240",
    "brown_multi_ma_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "moving average" in label and all(token in label for token in ("50", "100", "240")) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_multi_ma_data_provenance")):
        missing.append("brown_multi_ma_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    dot = normalized_status(first(state, "brown_qmp_dot"))
    ma_50 = number(first(state, "brown_ma_50"))
    ma_100 = number(first(state, "brown_ma_100"))
    ma_240 = number(first(state, "brown_ma_240"))
    if dot not in {"green", "red"} or None in {ma_50, ma_100, ma_240} or min(ma_50, ma_100, ma_240) <= 0:
        result["brown_multi_ma_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["QMP dot and finite positive 50/100/240 moving averages are required"]
        return result
    if dot == "green" and ma_50 > ma_100 > ma_240:
        result["brown_multi_ma_assessment"] = "BULLISH_50_100_240_ALIGNMENT"
        return with_direction(result, state, "BUY", "the green QMP trigger agrees with bullish 50/100/240 moving-average order")
    if dot == "red" and ma_50 < ma_100 < ma_240:
        result["brown_multi_ma_assessment"] = "BEARISH_50_100_240_ALIGNMENT"
        return with_direction(result, state, "SELL", "the red QMP trigger agrees with bearish 50/100/240 moving-average order")
    result["brown_multi_ma_assessment"] = "MA_ALIGNMENT_NOT_CLEARED"
    result["reasons"] = ["the 50/100/240 moving averages are not strictly ordered in the QMP direction"]
    return result
