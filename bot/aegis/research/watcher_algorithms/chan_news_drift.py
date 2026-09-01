"""Chan's post-event drift perspective with causal event timing."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "chan_news_drift"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_news_event_present",
    "chan_news_event_timing",
    "chan_news_open_return",
    "chan_news_baseline_std",
    "chan_news_event_type",
    "chan_news_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "chan_news_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("chan_news_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    present = first(state, "chan_news_event_present")
    timing = normalized_status(first(state, "chan_news_event_timing"))
    event_type = normalized_status(first(state, "chan_news_event_type"))
    open_return = number(first(state, "chan_news_open_return"))
    baseline = number(first(state, "chan_news_baseline_std"))
    if not volman_truth(present):
        result["chan_news_assessment"] = "NO_EVENT"
        result["view"] = "WAIT"
        result["reasons"] = ["no qualifying event was observed before the session open"]
        return result
    if timing != "after close before open" or not event_type:
        result["chan_news_assessment"] = "INVALID_EVENT_WINDOW"
        result["view"] = "WAIT"
        result["reasons"] = ["the drift study requires an event after the prior close and before the current open"]
        return result
    if open_return is None or baseline is None or baseline <= 0:
        result["chan_news_assessment"] = "INVALID_EVENT_RETURN"
        result["view"] = "WAIT"
        result["reasons"] = ["event return and baseline open-return volatility must be finite with positive volatility"]
        return result
    threshold = 0.5 * baseline
    result["chan_news_threshold"] = threshold
    if abs(open_return) < threshold or open_return == 0:
        result["chan_news_assessment"] = "INSUFFICIENT_EVENT_SURPRISE"
        result["view"] = "WAIT"
        result["reasons"] = ["the executable open move did not reach the source half-standard-deviation surprise threshold"]
        return result
    result["chan_news_assessment"] = "POST_EVENT_DRIFT"
    return with_direction(result, state, "BUY" if open_return > 0 else "SELL", "the observed post-event open move supplies the drift direction")
