"""John Carter's low/moderate-volume opening-gap fade perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_opening_gap_fade"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_gap_market",
    "carter_gap_previous_close",
    "carter_gap_open",
    "carter_gap_premarket_volume_regime",
    "carter_gap_session_minutes_et",
    "carter_gap_day_of_week",
    "carter_gap_special_day",
    "carter_gap_data_provenance",
)
MARKETS = {"es", "ym", "spy", "dia"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_gap_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_gap_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    market = normalized_status(first(state, "carter_gap_market")).replace(" ", "")
    if market not in MARKETS:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the source gap play is documented for observed index futures or their ETF mirrors"]
        return result

    previous_close = number(first(state, "carter_gap_previous_close"))
    opening_price = number(first(state, "carter_gap_open"))
    minutes = number(first(state, "carter_gap_session_minutes_et"))
    volume = normalized_status(first(state, "carter_gap_premarket_volume_regime"))
    weekday = normalized_status(first(state, "carter_gap_day_of_week"))
    if previous_close is None or opening_price is None or minutes is None or not 0 <= minutes < 1440:
        result["reasons"] = ["the cash-open prices and ET timestamp must be finite observations"]
        return result
    if minutes != 570:
        result["reasons"] = ["the gap is evaluated at the 9:30 ET cash open"]
        return result
    if weekday == "monday" or first(state, "carter_gap_special_day") is True:
        result["reasons"] = ["the source passes on Monday and other explicitly flagged low-probability special days"]
        return result
    if volume not in {"low", "moderate", "high"}:
        result["reasons"] = ["premarket volume must be classified as low, moderate, or high"]
        return result
    if volume == "high":
        result["reasons"] = ["high premarket volume marks a possible professional breakaway gap, which the source does not fade"]
        return result

    gap = opening_price - previous_close
    gap_points = abs(gap)
    minimum = {"ym": 10.0, "es": 1.0}.get(market)
    if minimum is None:
        minimum_met = first(state, "carter_gap_minimum_met")
        if minimum_met is not True:
            result["reasons"] = ["mirror-market gap size needs an observed instrument-specific minimum check"]
            return result
    elif gap_points < minimum:
        result["reasons"] = [f"the observed gap is below the {minimum:g}-point {market.upper()} minimum"]
        return result
    if gap == 0:
        result["reasons"] = ["a zero gap has no fade direction"]
        return result

    if market == "ym":
        stop_points = gap_points * 1.5 if gap_points < 40.0 else gap_points
    elif market == "es":
        stop_points = gap_points * 1.5 if gap_points < 4.0 else gap_points
    else:
        stop_points = number(first(state, "carter_gap_stop_points"))
        if stop_points is None or stop_points <= 0:
            result["reasons"] = ["mirror-market stop geometry must be supplied from observed instrument units"]
            return result
    target_points = gap_points * 0.5 if volume == "moderate" else gap_points
    signal = "BUY" if gap < 0 else "SELL"
    result.update({
        "carter_gap_points": gap_points,
        "carter_gap_stop_points": stop_points,
        "carter_gap_target_points": target_points,
        "carter_gap_fade_direction": signal,
    })
    return with_direction(result, state, signal, "a qualifying low/moderate-volume cash-open gap is faded toward the prior close")
