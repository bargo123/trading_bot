"""Seasonality perspective requiring an out-of-sample seasonal estimate."""
from __future__ import annotations

from ._common import base, explicitly_validated, first, number, text, values, with_direction

ALGORITHM_ID = "seasonality_context"
SOURCES = (
    "Day Trading and Swing Trading the Currency Market — Kathy Lien",
    "Systematic Trading — Robert Carver",
    "Evidence-Based Technical Analysis — David Aronson",
)
KEYS = (
    "seasonal_state", "seasonal_direction", "seasonal_expectancy", "seasonal_sample_n",
    "seasonal_period", "seasonal_validation", "seasonal_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("validated_seasonal_estimate",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    sample = number(first(state, "seasonal_sample_n"))
    expectancy = number(first(state, "seasonal_expectancy"))
    if sample is None or expectancy is None:
        result["view"] = "MISSING_DATA"
        result["applicability"] = "MISSING_DATA"
        result["missing_inputs"] = ["seasonal_sample_n", "seasonal_expectancy"]
        result["reasons"] = ["seasonality cannot be assessed without sample size and net expectancy"]
        return result
    if sample < 30:
        result["view"] = "WAIT"
        result["reasons"] = ["seasonal estimate has fewer than the minimum research observations"]
        return result
    validation = first(state, "seasonal_validation")
    if not explicitly_validated(validation, accepted=("validated", "walk forward", "sealed oos")):
        result["view"] = "WAIT"
        result["reasons"] = ["seasonal estimate is not validated out of sample"]
        return result
    if expectancy <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["seasonal net expectancy is not positive"]
        return result
    state_text = text(first(state, "seasonal_state", "seasonal_direction")).lower()
    if any(token in state_text for token in ("up", "bull", "buy", "favorable")):
        return with_direction(result, state, "BUY", "validated seasonal expectancy is positive for the upside")
    if any(token in state_text for token in ("down", "bear", "sell", "short")):
        return with_direction(result, state, "SELL", "validated seasonal expectancy is positive for the downside")
    result["view"] = "WAIT"
    result["reasons"] = ["positive seasonal expectancy has no directional annotation"]
    return result
