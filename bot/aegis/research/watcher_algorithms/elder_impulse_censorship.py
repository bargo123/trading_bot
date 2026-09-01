"""Alexander Elder's Impulse System as a prohibition/permission filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, side, values

ALGORITHM_ID = "elder_impulse_censorship"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = ("side", "elder_ema_slope", "elder_macd_histogram_slope", "elder_data_provenance")


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "elder_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("elder_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    ema = normalized_status(first(state, "elder_ema_slope"))
    macd = normalized_status(first(state, "elder_macd_histogram_slope"))
    rising = {"rising", "up", "increasing"}
    falling = {"falling", "down", "decreasing"}
    if ema in rising and macd in rising:
        impulse = "GREEN"
    elif ema in falling and macd in falling:
        impulse = "RED"
    elif (ema in rising | falling) and (macd in rising | falling):
        impulse = "BLUE"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["EMA and MACD-Histogram slopes are not classified"]
        return result
    candidate_side = side(state)
    if (impulse == "RED" and candidate_side == "BUY") or (impulse == "GREEN" and candidate_side == "SELL"):
        result["elder_impulse_state"] = impulse
        result["view"] = "WAIT"
        result["reasons"] = [f"the {impulse.lower()} Impulse bar prohibits this side"]
        return result
    result["elder_impulse_state"] = impulse
    result["elder_censorship"] = "PERMITTED"
    result["view"] = "PERMITTED"
    result["candidate_alignment"] = "PERMITTED"
    return result
