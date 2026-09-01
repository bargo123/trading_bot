"""Elder Impulse System: EMA slope and MACD-histogram slope agree."""
from __future__ import annotations

from ._common import absent, base, strings, values, with_direction

ALGORITHM_ID = "elder_impulse"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = ("ema_slope", "macd_histogram_slope", "impulse_state")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("ema_and_macd_slopes",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    ema = strings(state, "ema_slope")
    macd = strings(state, "macd_histogram_slope")
    impulse = strings(state, "impulse_state")
    if "green" in impulse and "up" in ema and "up" in macd:
        return with_direction(result, state, "BUY", "EMA and MACD-histogram slopes agree in a green impulse state")
    if "red" in impulse and "down" in ema and "down" in macd:
        return with_direction(result, state, "SELL", "EMA and MACD-histogram slopes agree in a red impulse state")
    result["view"] = "WAIT"
    result["reasons"] = ["Impulse System colors and component slopes do not align directionally"]
    return result
