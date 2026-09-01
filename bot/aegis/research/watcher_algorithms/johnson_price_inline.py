"""Price-inline perspective from Johnson's DMA text.

Price-inline is kept separate from adaptive shortfall because it requires an
explicit underlying schedule (for example POV or VWAP) plus price sensitivity.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "johnson_price_inline"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA",)
KEYS = (
    "side",
    "johnson_inline_benchmark_price",
    "johnson_inline_current_mid",
    "johnson_inline_baseline",
    "johnson_inline_adaptation",
    "johnson_inline_data_provenance",
)


def _adaptation(value):
    label = normalized_status(value)
    if label in {"aim", "aggressive in the money"} or "aggressive in the money" in label:
        return "AIM"
    if label in {"pim", "passive in the money"} or "passive in the money" in label:
        return "PIM"
    return None


def _baseline(value):
    label = normalized_status(value)
    if label in {"vwap", "twap", "pov"} or label.endswith(" vwap") or label.endswith(" pov"):
        return label.upper()
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("price_inline_baseline_and_quote",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    benchmark = number(first(state, "johnson_inline_benchmark_price"))
    current = number(first(state, "johnson_inline_current_mid"))
    baseline = _baseline(first(state, "johnson_inline_baseline"))
    adaptation = _adaptation(first(state, "johnson_inline_adaptation"))
    missing = [
        key for key, value in (
            ("side", candidate_side),
            ("johnson_inline_benchmark_price", benchmark),
            ("johnson_inline_current_mid", current),
            ("johnson_inline_baseline", baseline),
            ("johnson_inline_adaptation", adaptation),
        ) if value is None
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if benchmark <= 0 or current <= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["price-inline prices must be positive"]
        return result
    if not explicitly_observed(first(state, "johnson_inline_data_provenance"), accepted=("observed", "measured")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["johnson_inline_data_provenance"]
        result["reasons"] = ["price-inline comparison lacks observed quote provenance"]
        return result

    moneyness = (benchmark - current) / abs(benchmark) if candidate_side == "BUY" else (current - benchmark) / abs(benchmark)
    result["johnson_inline_baseline"] = baseline
    result["johnson_inline_adaptation"] = adaptation
    result["johnson_inline_price_moneyness"] = moneyness
    if adaptation == "AIM" and moneyness > 0:
        result["johnson_price_inline_assessment"] = "FAVORABLE_AIM"
        return with_direction(result, state, candidate_side, "price-inline AIM adapts the underlying schedule toward a favorable benchmark price")
    result["johnson_price_inline_assessment"] = "FAVORABLE_PIM_PASSIVITY" if moneyness > 0 else "ADVERSE_PRICE_WAIT"
    result["view"] = "WAIT"
    result["reasons"] = ["price-inline baseline is present but the selected adaptation does not call for aggressive entry"]
    return result
