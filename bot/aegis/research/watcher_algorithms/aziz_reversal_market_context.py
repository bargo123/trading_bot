"""Andrew Aziz's broad-market/sector context filter for reversals."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values

ALGORITHM_ID = "aziz_reversal_market_context"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_reversal_setup",
    "aziz_market_reversal_context",
    "aziz_sector_reversal_context",
    "aziz_reversal_context_data_provenance",
)
_CONTEXTS = {"with_underlying_move", "against_underlying_move", "mixed", "neutral"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "aziz_reversal_context_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("aziz_reversal_context_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    setup = normalized_status(first(state, "aziz_reversal_setup"))
    market = normalized_status(first(state, "aziz_market_reversal_context")).replace(" ", "_")
    sector = normalized_status(first(state, "aziz_sector_reversal_context")).replace(" ", "_")
    result["view"] = "WAIT"
    if setup not in {"bottom", "top"} or market not in _CONTEXTS or sector not in _CONTEXTS:
        result["aziz_reversal_context_assessment"] = "CONTEXT_INPUT_INVALID"
        result["reasons"] = ["the reversal must be bottom/top and both broad contexts must be observed categorical states"]
        return result

    result["aziz_reversal_context_assessment"] = (
        "REVERSAL_CONTEXT_CONFLICT"
        if market == sector == "with_underlying_move"
        else "CONTEXT_SUPPORTS_REVERSAL"
    )
    if result["aziz_reversal_context_assessment"] == "REVERSAL_CONTEXT_CONFLICT":
        result["reasons"] = [
            "the source warns against bottom/top reversals when both the overall market and sector continue the underlying move"
        ]
    else:
        result["reasons"] = [
            "the observed market/sector context is not jointly continuing the underlying move against the reversal thesis"
        ]
    result["aziz_reversal_setup"] = setup
    result["aziz_market_reversal_context"] = market
    result["aziz_sector_reversal_context"] = sector
    return result
