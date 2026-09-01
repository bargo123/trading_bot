"""Gray--Vogel 52-week-high momentum alternative, kept as a hypothesis."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction


ALGORITHM_ID = "gray_vogel_52_week_high"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_52w_price_ratio",
    "gray_52w_long_cutoff",
    "gray_52w_short_cutoff",
    "gray_52w_reference_window",
    "gray_52w_holding_months",
    "gray_52w_rebalance_frequency",
    "gray_52w_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable")) and any(
        token in label for token in ("observed", "measured", "historical")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_52w_data_provenance")):
        missing.append("gray_52w_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    ratio = number(first(state, "gray_52w_price_ratio"))
    long_cutoff = number(first(state, "gray_52w_long_cutoff"))
    short_cutoff = number(first(state, "gray_52w_short_cutoff"))
    holding_months = number(first(state, "gray_52w_holding_months"))
    window = normalized_status(first(state, "gray_52w_reference_window"))
    frequency = normalized_status(first(state, "gray_52w_rebalance_frequency"))
    if (
        any(value is None for value in (ratio, long_cutoff, short_cutoff, holding_months))
        or ratio < 0.0
        or short_cutoff < 0.0
        or long_cutoff <= short_cutoff
        or long_cutoff > 1.5
        or holding_months <= 0.0
        or window not in {"previous 52 weeks", "prior 52 weeks", "52 weeks"}
        or frequency not in {"monthly", "quarterly"}
    ):
        result["gray_52w_assessment"] = "INVALID_52_WEEK_INPUT"
        result["reasons"] = ["the reference ratio, dynamic cutoffs, holding window, and rebalance frequency must be explicit finite observations"]
        return result
    result.update({
        "gray_52w_price_ratio": ratio,
        "gray_52w_evidence_status": "HYPOTHESIS_ONLY",
    })
    if frequency == "monthly" and holding_months < 3.0:
        result["gray_52w_assessment"] = "MONTHLY_ROBUSTNESS_WARNING"
        result["warnings"] = ["the source reports that the monthly-rebalanced version breaks down in a reasonable robustness test"]
        result["reasons"] = ["the 52-week-high result is retained for research, not promoted as robust execution evidence"]
        return result
    if ratio >= long_cutoff:
        result["gray_52w_assessment"] = "NEAR_52_WEEK_HIGH_HYPOTHESIS"
        return with_direction(result, state, "BUY", "the observed price is in the supplied near-high reference bucket")
    if ratio <= short_cutoff:
        result["gray_52w_assessment"] = "FAR_FROM_52_WEEK_HIGH_HYPOTHESIS"
        return with_direction(result, state, "SELL", "the observed price is in the supplied far-from-high reference bucket")
    result["gray_52w_assessment"] = "NO_52_WEEK_BUCKET"
    result["reasons"] = ["the observed reference ratio is between the supplied high and low cutoffs"]
    return result
