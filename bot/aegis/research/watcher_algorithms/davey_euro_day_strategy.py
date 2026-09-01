"""Davey's Euro Day reversal-limit strategy, as a read-only bar replay."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values, with_direction


ALGORITHM_ID = "davey_euro_day_strategy"
SOURCES = ("Kevin J. Davey — Building Winning Algorithmic Trading Systems",)
KEYS = (
    "davey_day_time_hhmm",
    "davey_day_traded_this_session",
    "davey_day_xb",
    "davey_day_xb2",
    "davey_day_pip_add",
    "davey_day_stop_loss",
    "davey_day_profit_target",
    "davey_day_high_history",
    "davey_day_low_history",
    "davey_day_close_history",
    "davey_day_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if result and all(item is not None for item in result) else None


def _valid_hhmm(value):
    parsed = number(value)
    if parsed is None or parsed != int(parsed):
        return None
    parsed = int(parsed)
    return parsed if 0 <= parsed <= 2359 and parsed % 100 < 60 else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "davey_day_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("davey_day_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    time_hhmm = _valid_hhmm(first(state, "davey_day_time_hhmm"))
    xb = number(first(state, "davey_day_xb"))
    xb2 = number(first(state, "davey_day_xb2"))
    pip_add = number(first(state, "davey_day_pip_add"))
    stop_loss = number(first(state, "davey_day_stop_loss"))
    profit_target = number(first(state, "davey_day_profit_target"))
    highs = _series(first(state, "davey_day_high_history"))
    lows = _series(first(state, "davey_day_low_history"))
    closes = _series(first(state, "davey_day_close_history"))
    integer_params = lambda value: value is not None and value > 0 and value == int(value)
    if (
        time_hhmm is None
        or not integer_params(xb)
        or not integer_params(xb2)
        or pip_add is None
        or pip_add < 0
        or stop_loss is None
        or stop_loss <= 0
        or profit_target is None
        or profit_target <= 0
        or highs is None
        or lows is None
        or closes is None
        or len(highs) != len(lows)
        or len(lows) != len(closes)
        or len(closes) < max(int(xb), int(xb2) + 1)
    ):
        result["davey_day_action"] = "INVALID_DAY_PARAMETERS"
        result["reasons"] = ["the Euro Day replay requires valid session, history, and bracket inputs"]
        return result
    if time_hhmm >= 1500:
        result["davey_day_action"] = "OUTSIDE_DAY_SESSION"
        result["reasons"] = ["the source strategy only evaluates entries before 15:00"]
        return result
    if bool(first(state, "davey_day_traded_this_session")):
        result["davey_day_action"] = "SESSION_TRADE_ALREADY_USED"
        result["reasons"] = ["the source strategy permits at most one trade in the current session"]
        return result

    xb = int(xb)
    xb2 = int(xb2)
    current_high = highs[-1]
    current_low = lows[-1]
    current_close = closes[-1]
    prior_close = closes[-1 - xb2]
    short_trigger = current_high >= max(highs[-xb:]) and current_close < prior_close
    long_trigger = current_low <= min(lows[-xb:]) and current_close > prior_close
    if short_trigger and long_trigger:
        result["davey_day_action"] = "AMBIGUOUS_REVERSAL_BAR"
        result["reasons"] = ["both source reversal-limit conditions were true on the same bar"]
        return result
    if not short_trigger and not long_trigger:
        result["davey_day_action"] = "NO_REVERSAL_TRIGGER"
        result["reasons"] = ["the source high/low breakout and delayed-close reversal conditions were absent"]
        return result

    selected_side = "SELL" if short_trigger else "BUY"
    entry = current_high + pip_add / 10000.0 if selected_side == "SELL" else current_low - pip_add / 10000.0
    if entry <= 0:
        result["davey_day_action"] = "INVALID_DAY_ENTRY_PRICE"
        result["reasons"] = ["the source pip-offset limit entry is not positive"]
        return result
    result.update(
        {
            "davey_day_action": "PLACE_SHORT_LIMIT" if selected_side == "SELL" else "PLACE_LONG_LIMIT",
            "davey_day_selected_side": selected_side,
            "davey_day_entry_price": entry,
            "davey_day_stop_loss": stop_loss,
            "davey_day_profit_target": profit_target,
            "davey_day_lookback_xb": xb,
            "davey_day_delayed_close_xb2": xb2,
            "davey_day_pip_scale": 10000.0,
            "directional_claim": True,
        }
    )
    return with_direction(result, state, selected_side, "source Euro Day high/low reversal condition selected a limit entry")
