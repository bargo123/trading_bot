"""Jeremy du Plessis' Point-and-Figure horizontal-count perspective.

Horizontal counts measure the width of a completed congestion pattern.  The
source uses the row with the most activity (or another explicitly chosen
anchor row) and scales the width by the reversal size for three-box charts;
one-box counts use the box size directly.  This is a target study, not an
entry authority.
"""
from __future__ import annotations

from ._common import (
    absent,
    base,
    explicitly_observed,
    first,
    normalized_status,
    number,
    values,
    with_direction,
)

ALGORITHM_ID = "pf_horizontal_count_target"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 207-236"
KEYS = (
    "pf_box_reversal",
    "pf_box_size",
    "pf_count_method",
    "pf_count_direction",
    "pf_count_columns",
    "pf_count_anchor_price",
    "pf_count_anchor_role",
    "pf_count_pattern",
    "pf_count_width_fixed",
    "pf_count_activated",
    "pf_count_negated",
    "pf_data_provenance",
)


def _truthy(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid", "activated", "fixed"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])

    if not explicitly_observed(
        first(state, "pf_data_provenance"),
        accepted=("observed point and figure chart", "point and figure chart", "real point and figure"),
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_point_and_figure_chart"]
        result["reasons"] = ["horizontal counts require observed Point-and-Figure construction provenance"]
        return result

    if normalized_status(first(state, "pf_count_method")) != "horizontal":
        result["view"] = "WAIT"
        result["reasons"] = ["this perspective requires an explicitly identified horizontal count"]
        return result

    reversal = normalized_status(first(state, "pf_box_reversal"))
    multiplier = {"1 box": 1, "3 box": 3}.get(reversal)
    if multiplier is None:
        result["view"] = "WAIT"
        result["reasons"] = ["horizontal count scaling is supported only for the source's one-box or three-box charts"]
        return result

    count_direction = normalized_status(first(state, "pf_count_direction"))
    pattern = normalized_status(first(state, "pf_count_pattern")).replace(" ", "_")
    anchor_role = normalized_status(first(state, "pf_count_anchor_role")).replace(" ", "_")
    if count_direction not in {"up", "down"} or pattern not in {"bottom", "top", "congestion_bottom", "congestion_top"}:
        result["view"] = "WAIT"
        result["reasons"] = ["horizontal count direction and completed top/bottom congestion pattern must be explicit"]
        return result
    if anchor_role not in {"most_filled_row", "pattern_anchor_row", "count_row"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the count anchor must identify the observed active row of the pattern"]
        return result
    if multiplier == 3:
        required_pattern = "congestion_bottom" if count_direction == "up" else "congestion_top"
        if pattern != required_pattern:
            result["view"] = "WAIT"
            result["reasons"] = ["a three-box horizontal upside count comes from a congestion bottom and a downside count from a congestion top"]
            return result

    box_size = number(first(state, "pf_box_size"))
    columns = number(first(state, "pf_count_columns"))
    anchor = number(first(state, "pf_count_anchor_price"))
    if (
        box_size is None
        or box_size <= 0
        or columns is None
        or columns <= 0
        or not columns.is_integer()
        or anchor is None
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_horizontal_count_geometry"]
        result["reasons"] = ["box size, whole pattern width, and count-row anchor must be finite and positive where applicable"]
        return result

    result["pf_horizontal_count_columns"] = int(columns)
    result["pf_horizontal_count_multiplier"] = multiplier
    result["pf_horizontal_count_anchor"] = anchor
    result["pf_horizontal_count_target"] = anchor + (1 if count_direction == "up" else -1) * columns * box_size * multiplier
    result["pf_horizontal_count_formula"] = "anchor +/- (pattern_columns * box_size * reversal_multiplier)"

    if not _truthy(first(state, "pf_count_width_fixed")):
        result["pf_horizontal_count_status"] = "ESTABLISHMENT_PENDING"
        result["view"] = "WAIT"
        result["reasons"] = ["the congestion width has not been fixed by the observed pattern walls"]
        return result
    if _truthy(first(state, "pf_count_negated")):
        result["pf_horizontal_count_status"] = "NEGATED"
        result["view"] = "WAIT"
        result["reasons"] = ["the established horizontal count has been negated by the observed opposing move"]
        return result
    if not _truthy(first(state, "pf_count_activated")):
        result["pf_horizontal_count_status"] = "ESTABLISHED_NOT_ACTIVATED"
        result["view"] = "WAIT"
        result["reasons"] = ["the horizontal count is not active until the completed breakout fixes its direction"]
        return result

    result["pf_horizontal_count_status"] = "ACTIVE"
    return with_direction(
        result,
        state,
        "BUY" if count_direction == "up" else "SELL",
        "the observed horizontal Point-and-Figure count is fixed and activated",
    )
