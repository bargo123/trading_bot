"""John Carter's consecutive-close Scalper Alert reversal study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "carter_scalper_alert"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_scalper_closes",
    "carter_scalper_trigger_low",
    "carter_scalper_trigger_high",
    "carter_scalper_confirmation_close",
    "carter_scalper_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_scalper_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_scalper_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    closes = first(state, "carter_scalper_closes")
    if not isinstance(closes, (list, tuple)) or len(closes) < 3:
        result["view"] = "WAIT"
        result["reasons"] = ["the Scalper Alert needs at least three causal closes"]
        return result
    close_values = [number(value) for value in closes[-3:]]
    trigger_low = number(first(state, "carter_scalper_trigger_low"))
    trigger_high = number(first(state, "carter_scalper_trigger_high"))
    confirmation = number(first(state, "carter_scalper_confirmation_close"))
    if any(value is None for value in (*close_values, trigger_low, trigger_high, confirmation)):
        result["view"] = "WAIT"
        result["reasons"] = ["Scalper Alert prices must be finite numeric observations"]
        return result
    prior_low = number(first(state, "carter_scalper_prior_low"))
    prior_high = number(first(state, "carter_scalper_prior_high"))
    if close_values[0] < close_values[1] < close_values[2]:
        if prior_low is None:
            result["view"] = "WAIT"
            result["reasons"] = ["the long reversal needs the prior low for the higher-low trigger"]
            return result
        if trigger_low <= prior_low or confirmation <= trigger_high:
            result["view"] = "WAIT"
            result["reasons"] = ["three higher closes need a higher-low trigger and close above its high"]
            return result
        signal = "BUY"
    elif close_values[0] > close_values[1] > close_values[2]:
        if prior_high is None:
            result["view"] = "WAIT"
            result["reasons"] = ["the short reversal needs the prior high for the lower-high trigger"]
            return result
        if trigger_high >= prior_high or confirmation >= trigger_low:
            result["view"] = "WAIT"
            result["reasons"] = ["three lower closes need a lower-high trigger and close below its low"]
            return result
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the latest three closes are not a consecutive higher/lower sequence"]
        return result
    result["carter_scalper_close_sequence"] = close_values
    result["carter_scalper_trigger"] = "higher_low_then_close_above_trigger_high" if signal == "BUY" else "lower_high_then_close_below_trigger_low"
    return with_direction(result, state, signal, "three consecutive closes and the source price confirmation agree")
