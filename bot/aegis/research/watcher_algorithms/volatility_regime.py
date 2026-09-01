"""Volatility-regime and compression/expansion algorithm."""
from __future__ import annotations
from ._common import base, first, number, strings, values

ALGORITHM_ID = "volatility_regime"
SOURCES = ("Irene Aldridge — High-Frequency Trading", "Adam Grimes — The Art and Science of Technical Analysis", "Robert Carver — Systematic Trading", "Jean-Philippe Bouchaud — Trades, Quotes and Prices")
KEYS = ("volatility", "volatility_state", "volatility_expansion", "volatility_percentile", "atr", "realized_volatility", "regime", "compression", "expansion")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("volatility_state",))
    text = " ".join(str(value).lower() for _, value in found)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    expansion = number(first(state, "volatility_expansion"))
    if any(token in text for token in ("unstable", "extreme", "spike")):
        classification = "EXTREME"
    elif (
        (expansion is not None and expansion < 0.8)
        or "compressed" in text
        or ("compression" in text and "expansion" not in text)
    ):
        classification = "COMPRESSED"
    elif (
        (expansion is not None and expansion > 1.2)
        or any(token in text for token in ("expanding", "expansion"))
    ):
        classification = "EXPANDING"
    elif any(token in text for token in ("stable", "normal", "balanced")):
        classification = "STABLE"
    else:
        classification = "UNKNOWN"
    result["regime_classification"] = classification
    result["directional_claim"] = False
    if any(token in text for token in ("unstable", "extreme", "spike")):
        result["view"] = "WAIT"
        result["reasons"] = ["volatility regime is extreme or unstable"]
        result["warnings"] = ["short-horizon adverse selection and tail risk are elevated"]
        return result
    if "compression" in text and "expansion" not in text:
        result["view"] = "WAIT"
        result["reasons"] = ["compression is recorded without confirmed expansion"]
        return result
    result["view"] = "WAIT"
    result["reasons"] = ["volatility regime is recorded and is a context filter, not a directional claim"]
    return result
