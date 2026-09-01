"""Gray--Vogel look-back regime perspective.

The source separates short- and long-term reversal from intermediate-term
continuation.  The intermediate return explicitly skips the most recent
period, so this module requires that definition instead of treating a generic
recent return as interchangeable evidence.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "gray_vogel_lookback_regime"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_lookback_regime",
    "gray_short_term_return",
    "gray_intermediate_return",
    "gray_long_term_return",
    "gray_intermediate_skip_recent",
    "gray_data_provenance",
)


def _provenance_ok(value) -> bool:
    normalized = normalized_status(value)
    return bool(normalized) and not any(
        token in normalized for token in ("synthetic", "fixture", "unknown", "unavailable")
    ) and any(token in normalized for token in ("observed", "measured", "historical"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_data_provenance")):
        missing.append("gray_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    regime = normalized_status(first(state, "gray_lookback_regime")).replace(" ", "_")
    returns = {
        "short_term": number(first(state, "gray_short_term_return")),
        "intermediate": number(first(state, "gray_intermediate_return")),
        "long_term": number(first(state, "gray_long_term_return")),
    }
    if regime not in returns or any(value is None for value in returns.values()):
        result["gray_lookback_assessment"] = "INVALID_LOOKBACK_INPUT"
        result["reasons"] = ["the look-back regime and all three observed return definitions must be finite"]
        return result
    if regime == "intermediate" and first(state, "gray_intermediate_skip_recent") is not True:
        result["gray_lookback_assessment"] = "RECENT_PERIOD_NOT_SKIPPED"
        result["reasons"] = ["intermediate momentum is only comparable when the most recent period is explicitly skipped"]
        return result

    reference_return = returns[regime]
    result.update(
        {
            "gray_lookback_regime": regime,
            "gray_reference_return": reference_return,
            "gray_return_effect": "continuation" if regime == "intermediate" else "reversal",
        }
    )
    if reference_return == 0.0:
        result["gray_lookback_assessment"] = "NO_DIRECTIONAL_RETURN"
        result["reasons"] = ["the selected historical look-back has no directional return"]
        return result

    signal = "BUY" if reference_return > 0 else "SELL"
    if regime != "intermediate":
        signal = "SELL" if signal == "BUY" else "BUY"
    result["gray_lookback_assessment"] = "CONTINUATION" if regime == "intermediate" else "SHORT_OR_LONG_TERM_REVERSAL"
    return with_direction(
        result,
        state,
        signal,
        "the source's selected look-back effect is applied to the observed historical return",
    )
