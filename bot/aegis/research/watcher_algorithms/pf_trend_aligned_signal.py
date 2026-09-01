"""Jeremy du Plessis' preference for Point-and-Figure signals with the trend."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "pf_trend_aligned_signal"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 174-175"
KEYS = (
    "pf_prevailing_trend",
    "pf_signal_direction",
    "pf_signal_confirmed",
    "pf_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pf_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "pf_prevailing_trend"))
    signal = normalized_status(first(state, "pf_signal_direction"))
    if not _truthy(first(state, "pf_signal_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the Point-and-Figure signal is not confirmed"]
        return result
    if trend not in {"up", "down"} or signal not in {"up", "down"}:
        result["view"] = "WAIT"
        result["reasons"] = ["prevailing trend and signal direction must be explicit"]
        return result
    if trend != signal:
        result["view"] = "WAIT"
        result["reasons"] = ["countertrend Point-and-Figure signal is treated cautiously"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "confirmed Point-and-Figure signal agrees with the prevailing trend")
