"""Marcel Link's failed stochastic recovery perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "link_stochastic_failed_move"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_stochastic_failure_direction",
    "link_stochastic_fast_reversal",
    "link_stochastic_fast_crossed_slow",
    "link_stochastic_zone",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    failure_direction = normalized_status(first(state, "link_stochastic_failure_direction"))
    zone = normalized_status(first(state, "link_stochastic_zone"))
    if failure_direction not in {"up", "down"} or zone not in {"overbought", "oversold"}:
        result["link_stochastic_assessment"] = "INVALID_FAILURE_INPUT"
        result["reasons"] = ["stochastic failure direction and zone must be explicitly observed"]
        return result
    if first(state, "link_stochastic_fast_reversal") is not True or first(state, "link_stochastic_fast_crossed_slow") is not False:
        result["link_stochastic_assessment"] = "FAILED_MOVE_NOT_CONFIRMED"
        result["reasons"] = ["the fast stochastic must reverse and stall without crossing the slow line"]
        return result
    if (failure_direction == "up" and zone != "overbought") or (failure_direction == "down" and zone != "oversold"):
        result["link_stochastic_assessment"] = "ZONE_MISMATCH"
        result["reasons"] = ["the failed oscillator recovery is not located in its corresponding extreme zone"]
        return result

    signal = "SELL" if failure_direction == "up" else "BUY"
    result["link_stochastic_assessment"] = "FAILED_UPWARD_RECOVERY" if signal == "SELL" else "FAILED_DOWNWARD_RECOVERY"
    return with_direction(result, state, signal, "the oscillator's attempted recovery failed before crossing its slower line")
