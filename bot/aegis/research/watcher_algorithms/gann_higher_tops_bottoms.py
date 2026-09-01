"""W. D. Gann's higher-top/higher-bottom trend-form reading rule."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "gann_higher_tops_bottoms"
SOURCES = ("W. D. Gann — How to Make Profits in Commodities",)
SOURCE_PAGES = "pp. 43-46"
KEYS = (
    "gann_structure",
    "gann_structure_confirmed",
    "gann_structure_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "gann_structure_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("gann_structure_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "gann_structure_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the top/bottom progression is not confirmed from completed observations"]
        return result

    structure = normalized_status(first(state, "gann_structure")).replace("/", " and ")
    if structure == "higher tops and higher bottoms":
        result["gann_structure_assessment"] = "HIGHER_TOPS_HIGHER_BOTTOMS"
        return with_direction(result, state, "BUY", "observed higher tops and higher bottoms indicate an advancing trend")
    if structure == "lower tops and lower bottoms":
        result["gann_structure_assessment"] = "LOWER_TOPS_LOWER_BOTTOMS"
        return with_direction(result, state, "SELL", "observed lower tops and lower bottoms indicate a declining trend")

    result["view"] = "WAIT"
    result["reasons"] = ["Gann's directional form requires both tops and bottoms to progress consistently"]
    return result
