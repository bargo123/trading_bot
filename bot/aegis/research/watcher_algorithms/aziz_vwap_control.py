"""Andrew Aziz's VWAP institutional-control perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "aziz_vwap_control"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_vwap_relation",
    "aziz_vwap_retest_outcome",
    "aziz_vwap_session_phase",
    "aziz_vwap_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_vwap_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("aziz_vwap_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    relation = normalized_status(first(state, "aziz_vwap_relation"))
    outcome = normalized_status(first(state, "aziz_vwap_retest_outcome"))
    if relation not in {"above", "below"} or outcome not in {"held", "rejected", "sideways"}:
        result["view"] = "WAIT"
        result["aziz_vwap_assessment"] = "VWAP_INPUT_INVALID"
        result["reasons"] = ["VWAP relation and retest outcome must be explicit observed states"]
        return result
    if relation == "above" and outcome == "held":
        signal = "BUY"
        assessment = "BUYER_CONTROL_ABOVE_VWAP"
    elif relation == "below" and outcome == "rejected":
        signal = "SELL"
        assessment = "SELLER_CONTROL_BELOW_VWAP"
    else:
        result["view"] = "WAIT"
        result["aziz_vwap_assessment"] = "VWAP_CONTROL_UNRESOLVED"
        result["reasons"] = ["the source treats a held above-VWAP or rejected below-VWAP test as directional control"]
        return result
    result["aziz_vwap_assessment"] = assessment
    return with_direction(result, state, signal, "the observed VWAP interaction identifies which side controls price")
