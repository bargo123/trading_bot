"""The Ultimate Forex Trading System's news/support-resistance perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_news_sr_reaction"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_news_impact",
    "ultimate_news_currency",
    "ultimate_news_pair_affected",
    "ultimate_news_level_type",
    "ultimate_news_direction",
    "ultimate_news_stop_pips",
    "ultimate_news_target_pips",
    "ultimate_news_rr",
    "ultimate_news_minutes_to_release",
    "ultimate_news_entry_timing",
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
    impact = normalized_status(first(state, "ultimate_news_impact"))
    currency = normalized_status(first(state, "ultimate_news_currency"))
    level = normalized_status(first(state, "ultimate_news_level_type"))
    signal = normalized_status(first(state, "ultimate_news_direction")).upper()
    entry_timing = normalized_status(first(state, "ultimate_news_entry_timing"))
    stop = number(first(state, "ultimate_news_stop_pips"))
    target = number(first(state, "ultimate_news_target_pips"))
    rr = number(first(state, "ultimate_news_rr"))
    minutes = number(first(state, "ultimate_news_minutes_to_release"))
    if impact not in {"high", "medium"} or not currency or not _truthy(first(state, "ultimate_news_pair_affected")):
        result["view"] = "WAIT"
        result["reasons"] = ["the event must affect this pair and be a documented medium/high-impact release"]
        return result
    if level not in {"support", "resistance"} or signal not in {"BUY", "SELL"} or (level == "support" and signal != "BUY") or (level == "resistance" and signal != "SELL"):
        result["view"] = "WAIT"
        result["reasons"] = ["direction must agree with the observed support/resistance reaction"]
        return result
    if any(value is None for value in (stop, target, rr, minutes)) or not (10 <= stop <= 35) or target <= 0 or rr <= 2 or minutes < 0 or minutes > 15:
        result["view"] = "WAIT"
        result["reasons"] = ["news geometry must use a 10-35 pip stop, RR above 2, and a near-release entry"]
        return result
    if entry_timing != "pre release extreme":
        result["view"] = "WAIT"
        result["reasons"] = ["the source entry is taken at the pre-release high/low, not after the event"]
        return result
    result["ultimate_news_geometry"] = {"stop_pips": stop, "target_pips": target, "rr": rr}
    return with_direction(result, state, signal, "the affected pair is at a causal level with source-compliant news geometry")
