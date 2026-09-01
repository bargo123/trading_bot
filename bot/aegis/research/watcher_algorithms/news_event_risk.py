"""Scheduled-event and news-adverse-selection risk algorithm."""
from __future__ import annotations

from ._common import absent, base, first, strings, values

ALGORITHM_ID = "news_event_risk"
SOURCES = (
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "Irene Aldridge — High-Frequency Trading",
    "Barry Johnson — Algorithmic Trading and DMA",
    "Ernest Chan — Machine Trading",
)
KEYS = ("news_state", "event_risk", "calendar_state", "high_impact_news", "scheduled_event", "spread_around_news", "macro_event")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("event_calendar_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    high_impact = first(state, "high_impact_news")
    if high_impact is True or any(token in text for token in ("imminent", "high impact", "event risk", "news soon", "unknown calendar")):
        result["view"] = "WAIT"
        result["reasons"] = ["scheduled-event or news uncertainty raises adverse-selection risk"]
        result["warnings"] = ["directional prediction is not treated as sufficient during an unbounded event window"]
        return result
    if high_impact is False or any(token in text for token in ("no_high_impact_news", "clear calendar", "no event", "post_event")):
        result["view"] = "BUY" if str(first(state, "side", "position_side") or "").lower() == "buy" else "SELL" if str(first(state, "side", "position_side") or "").lower() == "sell" else "WAIT"
        result["reasons"] = ["recorded event state does not independently block the snapshot"]
        return result
    result["view"] = "WAIT"
    result["reasons"] = ["event state is present but its risk classification is unresolved"]
    return result
