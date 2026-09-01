"""Al Brooks breakout-mode strength and follow-through perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction
from ._deprado_common import provenance_ok

ALGORITHM_ID = "brooks_breakout_mode"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_breakout_mode_active",
    "brooks_breakout_direction",
    "brooks_breakout_body_fraction",
    "brooks_breakout_tail_fraction",
    "brooks_breakout_prior_follow_through",
    "brooks_breakout_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = str(value or "").strip().lower().replace("_", " ")
    if label in {"true", "yes", "observed", "confirmed", "present"}:
        return True
    if label in {"false", "no", "absent", "not confirmed"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    active = _boolean(first(state, "brooks_breakout_mode_active"))
    follow_through = _boolean(first(state, "brooks_breakout_prior_follow_through"))
    direction = str(first(state, "brooks_breakout_direction") or "").strip().upper()
    body = number(first(state, "brooks_breakout_body_fraction"))
    tails = number(first(state, "brooks_breakout_tail_fraction"))
    missing = [
        key for key, value in (
            ("brooks_breakout_mode_active", active),
            ("brooks_breakout_direction", direction if direction in {"BUY", "SELL"} else None),
            ("brooks_breakout_body_fraction", body),
            ("brooks_breakout_tail_fraction", tails),
            ("brooks_breakout_prior_follow_through", follow_through),
        ) if value is None
    ]
    provenance = first(state, "brooks_breakout_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("brooks_breakout_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["analysis_stage"] = "causal_breakout_mode_assessment"
    result["directional_claim"] = False
    if body is None or tails is None or not 0 <= body <= 1 or not 0 <= tails <= 1:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["breakout body and tail fractions must be bounded"]
        return result
    if not active:
        result["brooks_breakout_assessment"] = "BREAKOUT_MODE_INACTIVE"
        result["reasons"] = ["the copied state is not in breakout mode"]
        return result
    strong = body >= 0.6 and tails <= 0.4 and follow_through
    result["brooks_breakout_assessment"] = "CONFIRMED_BREAKOUT_MODE" if strong else "BREAKOUT_MODE_UNCONFIRMED"
    result["warnings"] = ["breakout direction is a research perspective and never execution authority"]
    if strong:
        result["directional_claim"] = True
        return with_direction(result, state, direction, "strong body, limited tails, and prior follow-through support the breakout direction")
    result["reasons"] = ["breakout strength or prior follow-through is insufficient for a directional view"]
    return result
