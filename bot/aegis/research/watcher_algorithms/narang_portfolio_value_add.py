"""Narang's with/without portfolio value-add comparison (Inside the Black Box, ch. 9)."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "narang_portfolio_value_add"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "narang_baseline_expectancy",
    "narang_with_strategy_expectancy",
    "narang_baseline_max_drawdown",
    "narang_with_strategy_max_drawdown",
    "narang_min_value_add",
    "narang_value_add_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_value_add_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("narang_value_add_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    baseline = number(first(state, "narang_baseline_expectancy"))
    with_strategy = number(first(state, "narang_with_strategy_expectancy"))
    baseline_dd = number(first(state, "narang_baseline_max_drawdown"))
    with_strategy_dd = number(first(state, "narang_with_strategy_max_drawdown"))
    minimum_add = number(first(state, "narang_min_value_add"))
    if (
        any(value is None for value in (baseline, with_strategy, baseline_dd, with_strategy_dd, minimum_add))
        or baseline_dd > 0.0
        or with_strategy_dd > 0.0
        or minimum_add < 0.0
    ):
        result["narang_portfolio_assessment"] = "INVALID_PORTFOLIO_COMPARISON"
        result["reasons"] = ["portfolio expectancy and non-positive drawdown observations must be finite"]
        return result

    expectancy_delta = with_strategy - baseline
    drawdown_delta = with_strategy_dd - baseline_dd
    result.update({
        "narang_expectancy_delta": expectancy_delta,
        "narang_drawdown_delta": drawdown_delta,
        "narang_min_value_add": minimum_add,
        "directional_claim": False,
    })
    if with_strategy_dd < baseline_dd:
        result["narang_portfolio_assessment"] = "DRAWDOWN_DETERIORATION"
        result["reasons"] = ["the added strategy makes observed maximum drawdown more negative"]
    elif expectancy_delta >= minimum_add:
        result["narang_portfolio_assessment"] = "VALUE_ADDED"
        result["reasons"] = ["the with-strategy replay improves expectancy without worsening maximum drawdown"]
    else:
        result["narang_portfolio_assessment"] = "NO_VALUE_ADD"
        result["reasons"] = ["the with-strategy replay does not clear the supplied minimum value-add hurdle"]
    return result
