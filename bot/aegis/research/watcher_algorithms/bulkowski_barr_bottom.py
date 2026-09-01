"""Bulkowski bump-and-run reversal bottom perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_barr_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "115-119"
KEYS = (
    "bulkowski_barr_type", "bulkowski_barr_lead_in_slope", "bulkowski_barr_bump_slope",
    "bulkowski_barr_lead_in_duration_days", "bulkowski_barr_lead_in_height", "bulkowski_barr_bump_height",
    "bulkowski_barr_breakout_direction", "bulkowski_barr_breakout_close_confirmed",
    "bulkowski_barr_breakout_price", "bulkowski_barr_high", "bulkowski_barr_low", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_barr_type")) != "bottom":
        result["reasons"] = ["this perspective requires a bump-and-run reversal bottom"]
        return result
    lead = number(first(state, "bulkowski_barr_lead_in_slope"))
    bump = number(first(state, "bulkowski_barr_bump_slope"))
    duration = number(first(state, "bulkowski_barr_lead_in_duration_days"))
    lead_height = number(first(state, "bulkowski_barr_lead_in_height"))
    bump_height = number(first(state, "bulkowski_barr_bump_height"))
    breakout = direction(state, "bulkowski_barr_breakout_direction")
    price = number(first(state, "bulkowski_barr_breakout_price"))
    high = number(first(state, "bulkowski_barr_high"))
    low = number(first(state, "bulkowski_barr_low"))
    if None in (lead, bump, duration, lead_height, bump_height, price, high, low) or breakout is None:
        result["reasons"] = ["BARR slopes, lead-in, bump, breakout, and range must be finite observations"]
        return result
    if lead >= 0 or bump >= lead or duration < 30 or lead_height <= 0 or bump_height < 2 * lead_height or high <= low:
        result["reasons"] = ["a BARR bottom needs a month-long falling lead-in and a materially deeper falling bump"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_barr_breakout_close_confirmed")):
        result["reasons"] = ["the BARR bottom requires a confirmed upward run breakout"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": price + height, "bulkowski_barr_height": height})
    return finish(result, state, "BUY", "a falling lead-in, deeper rounded bump, and confirmed upward run identify a BARR bottom")
