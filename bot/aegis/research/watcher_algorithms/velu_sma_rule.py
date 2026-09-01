"""Velu, Hardy, and Nehren's simple-moving-average ratio rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "velu_sma_rule"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_sma_prices",
    "velu_ma_mode",
    "velu_ma_upper_ratio",
    "velu_ma_lower_ratio",
    "velu_ma_data_provenance",
)


def _prices(state):
    raw = first(state, "velu_sma_prices")
    if not isinstance(raw, (list, tuple)):
        return None
    converted = [number(value) for value in raw]
    if not converted or any(value is None or value <= 0.0 for value in converted):
        return None
    return converted


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_ma_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("velu_ma_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    prices = _prices(state)
    mode = str(first(state, "velu_ma_mode") or "").strip().lower().replace(" ", "_")
    upper = number(first(state, "velu_ma_upper_ratio"))
    lower = number(first(state, "velu_ma_lower_ratio"))
    if (
        candidate_side is None
        or prices is None
        or mode not in {"reversal", "momentum"}
        or upper is None
        or lower is None
        or upper <= 1.0
        or not 0.0 < lower < 1.0
        or upper <= lower
    ):
        result["velu_sma_action"] = "INVALID_SMA_INPUT"
        result["reasons"] = [
            "the moving-average rule needs positive observed prices, a supported mode, and ordered ratio bands"
        ]
        return result

    average = sum(prices) / len(prices)
    current = prices[-1]
    ratio = average / current
    result.update(
        {
            "velu_sma_value": average,
            "velu_sma_current_price": current,
            "velu_sma_ratio": ratio,
            "velu_ma_mode": mode,
            "velu_ma_upper_ratio": upper,
            "velu_ma_lower_ratio": lower,
        }
    )
    if ratio > upper:
        signal = "BUY" if mode == "reversal" else "SELL"
        action = "REVERSAL_BUY" if mode == "reversal" else "MOMENTUM_SELL"
        return with_direction(
            {**result, "velu_sma_action": action},
            state,
            signal,
            "the observed price is below the SMA ratio band",
        )
    if ratio < lower:
        signal = "SELL" if mode == "reversal" else "BUY"
        action = "REVERSAL_SELL" if mode == "reversal" else "MOMENTUM_BUY"
        return with_direction(
            {**result, "velu_sma_action": action},
            state,
            signal,
            "the observed price is above the SMA ratio band",
        )
    result["velu_sma_action"] = "INSIDE_RATIO_BANDS"
    result["reasons"] = ["the observed SMA/current-price ratio is inside both configured bands"]
    return result
