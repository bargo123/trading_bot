"""Marcel Link's strong-stochastic, price-pullback retest perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, side, values, with_direction


ALGORITHM_ID = "link_stochastic_extreme_retest"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_stoch_strength",
    "link_stoch_retest_zone",
    "link_stoch_price_pullback_confirmed",
    "link_stoch_retest_confirmed",
    "link_stoch_retest_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_stoch_retest_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_stoch_retest_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    strength = normalized_status(first(state, "link_stoch_strength"))
    zone = normalized_status(first(state, "link_stoch_retest_zone"))
    pullback = first(state, "link_stoch_price_pullback_confirmed")
    retest = first(state, "link_stoch_retest_confirmed")
    if strength not in {"strong up", "strong down", "bullish", "bearish"} or zone not in {"oversold", "overbought"} or not isinstance(pullback, bool) or not isinstance(retest, bool):
        result["link_stoch_retest_action"] = "INVALID_RETEST_INPUT"
        result["reasons"] = ["stochastic strength, extreme zone, pullback, and retest must be explicit observations"]
        return result

    direction = "BUY" if strength in {"strong up", "bullish"} else "SELL"
    expected_zone = "oversold" if direction == "BUY" else "overbought"
    result.update({
        "link_stoch_retest_direction": direction,
        "link_stoch_retest_zone": zone,
        "directional_claim": True,
    })
    if direction != candidate_side or zone != expected_zone:
        result["link_stoch_retest_action"] = "ZONE_OR_SIDE_MISMATCH"
        result["view"] = "WAIT"
        result["reasons"] = ["the strong stochastic direction and retest extreme do not match the copied candidate side"]
        return result
    if not pullback:
        result["link_stoch_retest_action"] = "PULLBACK_NOT_CONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the required small price pullback has not been observed"]
        return result
    if not retest:
        result["link_stoch_retest_action"] = "RETEST_NOT_CONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the stochastic extreme retest has not been confirmed"]
        return result
    return with_direction(
        {**result, "link_stoch_retest_action": f"{candidate_side}_CONFIRMED_EXTREME_RETEST"},
        state,
        candidate_side,
        "strong observed stochastic direction and a confirmed price-pullback retest agree",
    )
