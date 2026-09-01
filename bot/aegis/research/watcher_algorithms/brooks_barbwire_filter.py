"""Al Brooks barbwire tight-range uncertainty perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import provenance_ok

ALGORITHM_ID = "brooks_barbwire_filter"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_barbwire_bars",
    "brooks_barbwire_doji_count",
    "brooks_barbwire_overlap_fraction",
    "brooks_barbwire_tail_fraction",
    "brooks_barbwire_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    bars = number(first(state, "brooks_barbwire_bars"))
    doji_count = number(first(state, "brooks_barbwire_doji_count"))
    overlap = number(first(state, "brooks_barbwire_overlap_fraction"))
    tails = number(first(state, "brooks_barbwire_tail_fraction"))
    missing = [
        key for key, value in (
            ("brooks_barbwire_bars", bars),
            ("brooks_barbwire_doji_count", doji_count),
            ("brooks_barbwire_overlap_fraction", overlap),
            ("brooks_barbwire_tail_fraction", tails),
        ) if value is None
    ]
    provenance = first(state, "brooks_barbwire_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("brooks_barbwire_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if bars < 0 or doji_count < 0 or not 0 <= overlap <= 1 or not 0 <= tails <= 1:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["barbwire counts and fractions must be finite and bounded"]
        return result
    detected = bars >= 3 and doji_count >= 1 and overlap >= 0.5 and tails >= 0.4
    result["analysis_stage"] = "causal_range_uncertainty"
    result["brooks_barbwire_assessment"] = "BARBWIRE_UNCERTAINTY" if detected else "NO_BARBWIRE"
    result["brooks_barbwire_detected"] = detected
    result["warnings"] = ["barbwire is an uncertainty filter; it supplies no BUY or SELL direction"]
    result["reasons"] = [
        "overlapping bars with a doji and prominent tails imply two-sided uncertainty"
        if detected else "observed range does not meet the operationalized barbwire conditions"
    ]
    return result
