"""Andrew Aziz's first/second bull-flag breakout perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "aziz_bull_flag_momentum"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_bull_flag_pole_direction",
    "aziz_bull_flag_consolidation",
    "aziz_bull_flag_consolidation_count",
    "aziz_bull_flag_breakout_confirmation",
    "aziz_bull_flag_volume_confirmation",
    "aziz_bull_flag_stop_defined",
    "aziz_bull_flag_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_bull_flag_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("aziz_bull_flag_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if str(first(state, "side") or "").upper() != "BUY":
        result["view"] = "WAIT"
        result["reasons"] = ["the source bull-flag perspective is long-only"]
        return result
    if normalized_status(first(state, "aziz_bull_flag_pole_direction")) not in {"up", "uptrend", "bullish"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the flag has no upward impulse pole"]
        return result
    count = number(first(state, "aziz_bull_flag_consolidation_count"))
    if count is None or count not in {1.0, 2.0}:
        result["view"] = "WAIT"
        result["reasons"] = ["only the first or second consolidation is source-supported"]
        return result
    checks = (
        ("aziz_bull_flag_consolidation", "a completed consolidation is not observed"),
        ("aziz_bull_flag_breakout_confirmation", "price has not broken the consolidation high"),
        ("aziz_bull_flag_volume_confirmation", "post-consolidation volume confirmation is missing"),
        ("aziz_bull_flag_stop_defined", "the consolidation invalidation stop is not defined"),
    )
    for key, reason in checks:
        if not volman_truth(first(state, key)):
            result["view"] = "WAIT"
            result["reasons"] = [reason]
            return result
    return with_direction(result, state, "BUY", "the first or second bull-flag consolidation has a confirmed, volume-supported upside break")
