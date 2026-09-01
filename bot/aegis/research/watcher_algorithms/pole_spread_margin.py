"""Andrew Pole's calibrated spread-margin reversion perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, values, with_direction
from ._deprado_common import provenance_ok

ALGORITHM_ID = "pole_spread_margin"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_spread_value",
    "pole_spread_min",
    "pole_spread_max",
    "pole_spread_margin_fraction",
    "pole_spread_stationarity",
    "pole_spread_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    current = number(first(state, "pole_spread_value"))
    minimum = number(first(state, "pole_spread_min"))
    maximum = number(first(state, "pole_spread_max"))
    margin = number(first(state, "pole_spread_margin_fraction"))
    missing = [
        key for key, value in (
            ("pole_spread_value", current),
            ("pole_spread_min", minimum),
            ("pole_spread_max", maximum),
            ("pole_spread_margin_fraction", margin),
        ) if value is None
    ]
    stationarity = first(state, "pole_spread_stationarity")
    if stationarity is None:
        missing.append("pole_spread_stationarity")
    provenance = first(state, "pole_spread_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("pole_spread_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if not explicitly_validated(stationarity, accepted=("validated", "stationary", "stationarity")):
        result["pole_spread_margin_assessment"] = "STATIONARITY_NOT_VALIDATED"
        result["reasons"] = ["spread-margin reversion requires an explicitly validated stationarity observation"]
        return result
    spread_range = maximum - minimum
    if spread_range <= 0 or not 0 < margin < 0.5:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["spread extremes must define a positive range and the margin must lie in (0, 0.5)"]
        return result
    lower = minimum + margin * spread_range
    upper = maximum - margin * spread_range
    result.update(
        {
            "analysis_stage": "causal_spread_margin_reversion",
            "pole_spread_lower_boundary": lower,
            "pole_spread_upper_boundary": upper,
            "pole_spread_margin_fraction": margin,
            "pole_spread_range": spread_range,
        }
    )
    if current <= lower:
        result["pole_spread_margin_assessment"] = "LOWER_MARGIN_BUY"
        return with_direction(result, state, "BUY", "the observed spread is at or below the lower margin inside its calibrated range")
    if current >= upper:
        result["pole_spread_margin_assessment"] = "UPPER_MARGIN_SELL"
        return with_direction(result, state, "SELL", "the observed spread is at or above the upper margin inside its calibrated range")
    result["pole_spread_margin_assessment"] = "INSIDE_MARGIN_BAND"
    result["reasons"] = ["the observed spread is inside the calibrated outer margin band"]
    return result
