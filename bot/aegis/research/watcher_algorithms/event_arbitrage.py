"""Point-in-time event-study perspective for the read-only Watcher.

Event trading requires a timestamped release, a surprise relative to an
expectation, and a measured historical response for the relevant instrument
and window. Generic news labels are not enough. This evaluator never submits
orders and never uses post-decision prices as entry evidence.
"""
from __future__ import annotations

from datetime import datetime
import re

from ._common import absent, base, direction, explicitly_confirmed, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "event_arbitrage"
SOURCES = (
    "Irene Aldridge — High-Frequency Trading",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "David Aronson — Evidence-Based Technical Analysis",
)
KEYS = (
    "event_state",
    "event_as_of",
    "decision_as_of",
    "event_window_s",
    "event_surprise",
    "event_response_direction",
    "event_response_confirmation",
    "event_response_persistence",
    "event_oos_n",
    "event_expectancy_net",
    "event_provenance",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _timestamp(value):
    label = str(value or "").strip()
    if not label:
        return None
    try:
        return datetime.fromisoformat(label.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("timestamped_event_study",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False

    event_time = _timestamp(first(state, "event_as_of"))
    decision_time = _timestamp(first(state, "decision_as_of"))
    if event_time is None or decision_time is None:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["event_and_decision_timestamps"]
        result["reasons"] = ["event evidence must be timestamped relative to the copied decision"]
        return result
    if event_time > decision_time:
        result["event_assessment"] = "NOT_RELEASED"
        result["reasons"] = ["the event was not released at the recorded decision time"]
        return result

    window = number(first(state, "event_window_s"))
    surprise = number(first(state, "event_surprise"))
    oos_n = number(first(state, "event_oos_n"))
    expectancy = number(first(state, "event_expectancy_net"))
    if window is None or window <= 0 or surprise is None or oos_n is None or oos_n <= 0 or expectancy is None:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["event_window_surprise_oos_net_economics"]
        result["reasons"] = ["event arbitrage needs a finite window, surprise, positive OOS sample, and net expectancy"]
        return result
    if not explicitly_observed(first(state, "event_provenance"), accepted=("timestamped event study", "observed event study")):
        result["event_assessment"] = "UNKNOWN"
        result["warnings"] = ["event provenance is missing, synthetic, proxy, or unverified"]
        result["reasons"] = ["historical event response is not sufficiently observed"]
        return result
    event_state = normalized_status(first(state, "event_state"))
    if not any(_has_token(event_state, marker) for marker in ("released", "announced", "occurred", "post event")):
        result["event_assessment"] = "NOT_RELEASED"
        result["reasons"] = ["event state is not an observed release/post-event state"]
        return result
    response = direction(first(state, "event_response_direction"))
    if response is None or not explicitly_confirmed(first(state, "event_response_confirmation")):
        result["event_assessment"] = "UNRESOLVED"
        result["reasons"] = ["the measured event response has no explicit confirmed direction"]
        return result
    if expectancy <= 0:
        result["event_assessment"] = "NEGATIVE_NET_EDGE"
        result["reasons"] = ["the historical event response is not positive after recorded costs"]
        return result

    result["event_assessment"] = "MEASURED"
    result["event_window_s"] = window
    result["event_oos_n"] = int(oos_n) if oos_n.is_integer() else oos_n
    result["event_expectancy_net"] = expectancy
    return with_direction(result, state, response, "timestamped event study supports the recorded post-release response")
