"""Root-cause process diagnostic from Tendler's Mental Game of Trading."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "tendler_process_error"
SOURCES = ("Jared Tendler — The Mental Game of Trading",)
KEYS = (
    "tendler_performance_state",
    "tendler_emotion_signal",
    "tendler_root_cause_identified",
    "tendler_execution_error",
    "tendler_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable")
    ) and any(token in label for token in ("observed", "timestamped", "journal"))


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "identified", "present"}


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "tendler_data_provenance")):
        missing.append("tendler_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    performance = normalized_status(first(state, "tendler_performance_state")).upper()
    emotion = normalized_status(first(state, "tendler_emotion_signal"))
    error = normalized_status(first(state, "tendler_execution_error"))
    if performance not in {"A", "B", "C"} or not error:
        result["tendler_assessment"] = "INVALID_PROCESS_STATE"
        result["reasons"] = ["performance state and execution error must be recorded explicitly"]
    elif performance == "C" or emotion not in {"", "neutral", "stable", "calm", "focused", "clear"}:
        result["tendler_assessment"] = "ROOT_CAUSE_REVIEW"
        result["reasons"] = ["emotion is treated as a signal to investigate the underlying execution error"]
    elif _truth(first(state, "tendler_root_cause_identified")):
        result["tendler_assessment"] = "LEARNING_REVIEW"
        result["reasons"] = ["a stable technical error is recorded with an identified root cause for correction"]
    else:
        result["tendler_assessment"] = "ROOT_CAUSE_MISSING"
        result["reasons"] = ["the process error is recorded but its underlying cause is not identified"]
    result["tendler_performance_state"] = performance
    return result

