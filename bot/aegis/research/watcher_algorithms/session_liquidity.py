"""Session, market-hours, and liquidity-state algorithm."""
from __future__ import annotations
from ._common import base, first, strings, values

ALGORITHM_ID = "session_liquidity"
SOURCES = ("Irene Aldridge — High-Frequency Trading", "Kathy Lien — Day Trading and Swing Trading the Currency Market", "James Dalton — Markets in Profile", "Barry Johnson — Algorithmic Trading and DMA")
KEYS = ("session", "session_state", "liquidity", "market_open", "market_state", "news_state")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("session_or_liquidity",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, *KEYS)
    session = str(first(state, "session") or "").strip().lower()
    result["session_class"] = {
        "new_york": "NEW_YORK",
        "london": "LONDON",
        "asia": "ASIA",
        "off_session": "OFF_SESSION",
    }.get(session, "UNKNOWN")
    if first(state, "market_open") is False or any(token in text for token in ("closed", "halt", "no session")):
        result["liquidity_assessment"] = "CLOSED"
        result["view"] = "WAIT"
        result["reasons"] = ["market session or liquidity state is not executable"]
        return result
    if any(token in text for token in ("illiquid", "low liquidity", "thin")):
        result["liquidity_assessment"] = "LOW"
        result["view"] = "WAIT"
        result["reasons"] = ["observed session has thin or illiquid conditions"]
        return result
    result["liquidity_assessment"] = "OBSERVED"
    result["view"] = "WAIT"
    result["reasons"] = ["session/liquidity context is present without a directional claim"]
    return result
