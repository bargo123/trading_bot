"""Marcel Link's RSI pattern/trendline confirmation perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, side, values, with_direction


ALGORITHM_ID = "link_rsi_pattern_break"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_rsi_pattern_direction",
    "link_rsi_pattern_confirmed",
    "link_rsi_pattern_name",
    "link_rsi_pattern_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_rsi_pattern_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_rsi_pattern_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    pattern_direction = normalized_status(first(state, "link_rsi_pattern_direction"))
    pattern_name = str(first(state, "link_rsi_pattern_name") or "").strip()
    confirmed = first(state, "link_rsi_pattern_confirmed")
    if pattern_direction not in {"up", "down", "bullish", "bearish"} or not pattern_name or not isinstance(confirmed, bool):
        result["link_rsi_pattern_action"] = "INVALID_PATTERN_INPUT"
        result["reasons"] = ["RSI pattern direction, name, and confirmation must be explicit observed inputs"]
        return result
    direction = "BUY" if pattern_direction in {"up", "bullish"} else "SELL"
    result.update({"link_rsi_pattern_name": pattern_name, "link_rsi_pattern_direction": direction, "directional_claim": True})
    if not confirmed:
        result["link_rsi_pattern_action"] = "PATTERN_NOT_CONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the observed RSI pattern or trendline break is not confirmed"]
        return result
    if direction != candidate_side:
        result["link_rsi_pattern_action"] = "PATTERN_OPPOSES_CANDIDATE"
        result["view"] = "WAIT"
        result["reasons"] = ["the confirmed RSI pattern direction opposes the copied candidate side"]
        return result
    return with_direction(
        {**result, "link_rsi_pattern_action": f"{candidate_side}_CONFIRMED_PATTERN_BREAK"},
        state,
        candidate_side,
        "the observed RSI pattern or trendline break is confirmed in the candidate direction",
    )
