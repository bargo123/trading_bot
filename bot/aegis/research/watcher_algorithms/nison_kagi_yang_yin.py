"""Nison Kagi yang/yin transition and shoulder/waist structure perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_kagi_yang_yin"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_kagi_line",
    "nison_kagi_structure",
    "nison_kagi_transition",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    line = normalized_status(first(state, "nison_kagi_line"))
    structure = normalized_status(first(state, "nison_kagi_structure"))
    if not volman_truth(first(state, "nison_kagi_transition")):
        result["view"] = "WAIT"
        result["reasons"] = ["Kagi yin/yang transition is not confirmed"]
        return result
    if line == "yang" and "rising shoulder" in structure and "rising waist" in structure:
        return with_direction(result, state, "BUY", "thick yang line with rising shoulders and waists")
    if line == "yin" and "falling shoulder" in structure and "falling waist" in structure:
        return with_direction(result, state, "SELL", "thin yin line with falling shoulders and waists")
    result["view"] = "WAIT"
    result["reasons"] = ["Kagi line and shoulder/waist structure do not agree"]
    return result
