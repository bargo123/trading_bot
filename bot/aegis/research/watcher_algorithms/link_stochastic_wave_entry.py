"""Marcel Link's two-line stochastic wave entry perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "link_stochastic_wave_entry"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_stoch_fast",
    "link_stoch_slow",
    "link_stoch_fast_previous",
    "link_stoch_slow_previous",
    "link_stoch_oversold",
    "link_stoch_overbought",
    "link_stoch_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "link_stoch_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "runtime")):
        missing.append("link_stoch_data_provenance")
    if side(state) is None:
        missing.append("side")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    fast = number(first(state, "link_stoch_fast"))
    slow = number(first(state, "link_stoch_slow"))
    fast_previous = number(first(state, "link_stoch_fast_previous"))
    slow_previous = number(first(state, "link_stoch_slow_previous"))
    oversold = number(first(state, "link_stoch_oversold"))
    overbought = number(first(state, "link_stoch_overbought"))
    if (
        any(value is None for value in (fast, slow, fast_previous, slow_previous, oversold, overbought))
        or any(not 0.0 <= value <= 100.0 for value in (fast, slow, fast_previous, slow_previous, oversold, overbought))
        or not oversold < overbought
    ):
        result["link_stoch_action"] = "INVALID_STOCHASTIC_INPUT"
        result["reasons"] = ["stochastic lines and thresholds must be bounded observations with oversold below overbought"]
        return result

    above_oversold = fast > oversold and slow > oversold
    below_overbought = fast < overbought and slow < overbought
    above_overbought = fast > overbought and slow > overbought
    below_oversold = fast < oversold and slow < oversold
    rising = fast > fast_previous and slow > slow_previous
    falling = fast < fast_previous and slow < slow_previous
    not_turning_lower = fast >= fast_previous and slow >= slow_previous
    not_turning_higher = fast <= fast_previous and slow <= slow_previous
    result.update(
        {
            "link_stoch_lines_above_oversold": above_oversold,
            "link_stoch_lines_below_overbought": below_overbought,
            "link_stoch_lines_above_overbought": above_overbought,
            "link_stoch_lines_below_oversold": below_oversold,
            "link_stoch_both_lines_rising": rising,
            "link_stoch_both_lines_falling": falling,
            "link_stoch_extreme_not_turning_lower": not_turning_lower,
            "link_stoch_extreme_not_turning_higher": not_turning_higher,
            "directional_claim": True,
        }
    )
    if candidate_side == "BUY" and above_overbought and not_turning_lower:
        return with_direction(
            {**result, "link_stoch_action": "BUY_OVERBOUGHT_TREND_CONTINUATION"},
            state,
            "BUY",
            "both stochastic lines remain above overbought without turning lower",
        )
    if candidate_side == "SELL" and below_oversold and not_turning_higher:
        return with_direction(
            {**result, "link_stoch_action": "SELL_OVERSOLD_TREND_CONTINUATION"},
            state,
            "SELL",
            "both stochastic lines remain below oversold without turning higher",
        )
    if candidate_side == "BUY" and above_oversold and rising:
        return with_direction(
            {**result, "link_stoch_action": "BUY_BOTH_LINES_RISING_ABOVE_OVERSOLD"},
            state,
            "BUY",
            "both stochastic lines are above oversold and rising into a wave",
        )
    if candidate_side == "SELL" and below_overbought and falling:
        return with_direction(
            {**result, "link_stoch_action": "SELL_BOTH_LINES_FALLING_BELOW_OVERBOUGHT"},
            state,
            "SELL",
            "both stochastic lines are below overbought and falling into a wave",
        )
    result["link_stoch_action"] = "NO_STOCHASTIC_WAVE"
    result["reasons"] = ["both stochastic lines do not meet the source wave-direction and threshold conditions"]
    return result
