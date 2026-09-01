"""The Holy Grail case study's warning about trend-system regime failure."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "grail_regime_failure_warning"
SOURCES = ("James Windsor — The Holy Grail Forex Trading System",)
KEYS = (
    "grail_strategy_regime",
    "grail_intraday_trend_present",
    "grail_regime_observed",
    "grail_regime_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "grail_regime_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("grail_regime_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    regime = normalized_status(first(state, "grail_strategy_regime"))
    if regime not in {"trending", "trend", "range", "ranging", "reversal", "choppy"}:
        result["grail_regime_assessment"] = "REGIME_INVALID"
        result["reasons"] = ["the source comparison requires an observed trend or non-trend regime"]
        return result
    if not _truthy(first(state, "grail_regime_observed")):
        result["grail_regime_assessment"] = "REGIME_NOT_CONFIRMED"
        result["reasons"] = ["regime status must be observed at the decision time"]
        return result
    if regime in {"trending", "trend"} and _truthy(first(state, "grail_intraday_trend_present")):
        result["grail_regime_assessment"] = "REGIME_FITS"
        result["reasons"] = ["the source trend-following system is studied only while an intraday trend is present"]
        return result
    result["grail_regime_assessment"] = "SYSTEM_NOT_FIT"
    result["warnings"] = ["the source reports severe deterioration when its trend system meets a non-trending regime"]
    result["reasons"] = ["range/reversal conditions are a failure warning for the source trend-following system"]
    return result
