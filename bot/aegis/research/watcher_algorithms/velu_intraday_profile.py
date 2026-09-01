"""Velu, Hardy, and Nehren's intraday profile normalization perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "velu_intraday_profile"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_profile_current_volume",
    "velu_profile_expected_volume",
    "velu_profile_current_volatility",
    "velu_profile_expected_volatility",
    "velu_profile_current_spread",
    "velu_profile_expected_spread",
    "velu_profile_spread_limit_multiplier",
    "velu_profile_activity_spike_multiplier",
    "velu_profile_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_profile_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_profile_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    current_volume = number(first(state, "velu_profile_current_volume"))
    expected_volume = number(first(state, "velu_profile_expected_volume"))
    current_volatility = number(first(state, "velu_profile_current_volatility"))
    expected_volatility = number(first(state, "velu_profile_expected_volatility"))
    current_spread = number(first(state, "velu_profile_current_spread"))
    expected_spread = number(first(state, "velu_profile_expected_spread"))
    spread_limit = number(first(state, "velu_profile_spread_limit_multiplier"))
    activity_limit = number(first(state, "velu_profile_activity_spike_multiplier"))
    if (
        current_volume is None
        or expected_volume is None
        or current_volatility is None
        or expected_volatility is None
        or current_spread is None
        or expected_spread is None
        or spread_limit is None
        or activity_limit is None
        or expected_volume <= 0
        or expected_volatility <= 0
        or expected_spread <= 0
        or current_volume < 0
        or current_volatility < 0
        or current_spread < 0
        or spread_limit <= 0
        or activity_limit <= 0
    ):
        result["velu_profile_action"] = "INVALID_PROFILE_INPUT"
        result["reasons"] = [
            "intraday profile normalization needs positive measured baselines and nonnegative current observations"
        ]
        return result

    volume_multiplier = current_volume / expected_volume
    volatility_multiplier = current_volatility / expected_volatility
    spread_multiplier = current_spread / expected_spread
    result.update(
        {
            "velu_volume_multiplier": volume_multiplier,
            "velu_volatility_multiplier": volatility_multiplier,
            "velu_spread_multiplier": spread_multiplier,
        }
    )
    if spread_multiplier > spread_limit:
        result["velu_profile_action"] = "SPREAD_ABOVE_PROFILE"
        result["reasons"] = [
            "the measured spread is above its calibrated intraday profile limit"
        ]
    elif volume_multiplier >= activity_limit or volatility_multiplier >= activity_limit:
        result["velu_profile_action"] = "ACTIVITY_PROFILE_SHOCK"
        result["reasons"] = [
            "measured volume or volatility is an activity shock relative to its calibrated intraday profile"
        ]
    else:
        result["velu_profile_action"] = "PROFILE_ALIGNED"
        result["reasons"] = [
            "measured volume, volatility, and spread remain within the supplied intraday profile"
        ]
    return result
