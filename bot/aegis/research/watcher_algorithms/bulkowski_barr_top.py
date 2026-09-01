"""Bulkowski bump-and-run reversal top perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_barr_top"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "132-135"
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
    if normalized_status(first(state, "bulkowski_barr_type")) != "top":
        result["reasons"] = ["this perspective requires a bump-and-run reversal top"]
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
    if lead <= 0 or bump <= lead or duration < 30 or lead_height <= 0 or bump_height < 2 * lead_height or high <= low:
        result["reasons"] = ["a BARR top needs a month-long rising lead-in and a materially steeper rising bump"]
        return result
    if breakout != "DOWN" or not observed_bool(first(state, "bulkowski_barr_breakout_close_confirmed")):
        result["reasons"] = ["the BARR top requires a confirmed downward run breakout"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": price - height, "bulkowski_barr_height": height})
    return finish(result, state, "SELL", "a rising lead-in, steeper rounded bump, and confirmed downward run identify a BARR top")
