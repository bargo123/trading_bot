"""Jeremy du Plessis' activated three-box vertical-count perspective.

The count is a Point-and-Figure target, not a standalone entry rule.  A
three-box count is only usable after the counted column is fixed and the
breakout has activated it.  The Watcher therefore records the target and its
state, while remaining research-only.
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

ALGORITHM_ID = "pf_vertical_count_target"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 221-228"
KEYS = (
    "pf_box_reversal",
    "pf_box_size",
    "pf_count_direction",
    "pf_count_column_type",
    "pf_count_column_boxes",
    "pf_count_anchor_price",
    "pf_count_anchor_role",
    "pf_count_source",
    "pf_count_column_fixed",
    "pf_count_activated",
    "pf_count_negated",
    "pf_data_provenance",
)

_UP_SOURCES = {"first_move_off_bottom", "mini_bottom", "breakout_column", "significant_breakout"}
_DOWN_SOURCES = {"first_move_off_top", "mini_top", "breakout_column", "significant_breakout"}


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
        result["reasons"] = ["vertical counts require observed Point-and-Figure construction provenance"]
        return result

    reversal = normalized_status(first(state, "pf_box_reversal"))
    if reversal != "3 box":
        result["view"] = "WAIT"
        result["reasons"] = ["the vertical-count formula in this perspective is defined for three-box reversal charts"]
        return result

    count_direction = normalized_status(first(state, "pf_count_direction"))
    column_type = normalized_status(first(state, "pf_count_column_type"))
    source = normalized_status(first(state, "pf_count_source")).replace(" ", "_")
    anchor_role = normalized_status(first(state, "pf_count_anchor_role")).replace(" ", "_")
    if count_direction not in {"up", "down"} or column_type not in {"x", "o"}:
        result["view"] = "WAIT"
        result["reasons"] = ["count direction and counted column type must be explicit up/X or down/O observations"]
        return result
    if (count_direction == "up" and column_type != "x") or (count_direction == "down" and column_type != "o"):
        result["view"] = "WAIT"
        result["reasons"] = ["an upside count must count an X column and a downside count must count an O column"]
        return result
    allowed_sources = _UP_SOURCES if count_direction == "up" else _DOWN_SOURCES
    if source not in allowed_sources:
        result["view"] = "WAIT"
        result["reasons"] = ["the counted column is not an observed first move, mini-extreme, or significant breakout column"]
        return result

    expected_anchor_role = (
        "preceding_opposite_column_low" if count_direction == "up" else "preceding_opposite_column_high"
    )
    if anchor_role != expected_anchor_role:
        result["view"] = "WAIT"
        result["reasons"] = ["the count anchor must be the extreme of the immediately preceding opposite column"]
        return result

    box_size = number(first(state, "pf_box_size"))
    column_boxes = number(first(state, "pf_count_column_boxes"))
    anchor = number(first(state, "pf_count_anchor_price"))
    if (
        box_size is None
        or box_size <= 0
        or column_boxes is None
        or column_boxes <= 0
        or not column_boxes.is_integer()
        or anchor is None
    ):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_three_box_count_geometry"]
        result["reasons"] = ["box size, whole counted-column boxes, and anchor price must be finite and positive where applicable"]
        return result

    fixed = _truthy(first(state, "pf_count_column_fixed"))
    activated = _truthy(first(state, "pf_count_activated"))
    negated = _truthy(first(state, "pf_count_negated"))
    result["pf_vertical_count_boxes"] = int(column_boxes)
    result["pf_vertical_count_multiplier"] = 3
    result["pf_vertical_count_anchor"] = anchor
    result["pf_vertical_count_target"] = anchor + (1 if count_direction == "up" else -1) * column_boxes * box_size * 3
    result["pf_vertical_count_formula"] = "anchor +/- (counted_column_boxes * box_size * 3)"

    if not fixed:
        result["pf_vertical_count_status"] = "ESTABLISHMENT_PENDING"
        result["view"] = "WAIT"
        result["reasons"] = ["the counted column has not yet been fixed by the opposite reversal column"]
        return result
    if negated:
        result["pf_vertical_count_status"] = "NEGATED"
        result["view"] = "WAIT"
        result["reasons"] = ["the established count has been negated by the observed opposing move"]
        return result
    if not activated:
        result["pf_vertical_count_status"] = "ESTABLISHED_NOT_ACTIVATED"
        result["view"] = "WAIT"
        result["reasons"] = ["the established target is not active until price breaks the counted-column extreme"]
        return result

    result["pf_vertical_count_status"] = "ACTIVE"
    return with_direction(
        result,
        state,
        "BUY" if count_direction == "up" else "SELL",
        "the observed three-box vertical count is fixed and activated",
    )
