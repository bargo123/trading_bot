"""The Ultimate Forex Trading System's repeated support/resistance test study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_double_triple_test"
SOURCES = ("Mostafa Afshari — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_multi_test_type",
    "ultimate_multi_test_zone",
    "ultimate_multi_test_count",
    "ultimate_multi_test_bounce_confirmed",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = normalized_status(first(state, "ultimate_multi_test_type"))
    zone = normalized_status(first(state, "ultimate_multi_test_zone"))
    count = number(first(state, "ultimate_multi_test_count"))
    expected_count = {"double bottom": 2, "double top": 2, "triple bottom": 3, "triple top": 3}.get(pattern)
    if expected_count is None or count != expected_count:
        result["ultimate_multi_test_assessment"] = "TEST_COUNT_INVALID"
        result["reasons"] = ["the observed double/triple pattern must contain its corresponding two or three tests"]
        return result
    if ("bottom" in pattern and zone != "support") or ("top" in pattern and zone != "resistance"):
        result["ultimate_multi_test_assessment"] = "ZONE_PATTERN_MISMATCH"
        result["reasons"] = ["bottom tests belong at support and top tests belong at resistance"]
        return result
    if not _truthy(first(state, "ultimate_multi_test_bounce_confirmed")):
        result["ultimate_multi_test_assessment"] = "BOUNCE_NOT_CONFIRMED"
        result["reasons"] = ["a repeated test is only a setup until the bounce is observed"]
        return result
    signal = "BUY" if "bottom" in pattern else "SELL"
    result["ultimate_multi_test_assessment"] = "CONFIRMED_BOTTOM_BOUNCE" if signal == "BUY" else "CONFIRMED_TOP_BOUNCE"
    result["ultimate_multi_test_count"] = int(count)
    return with_direction(result, state, signal, "the repeated test has produced a confirmed source-aligned bounce")
