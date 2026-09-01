"""Aldridge trade-direction provenance diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values

ALGORITHM_ID = "aldridge_trade_direction_uncertainty"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_trade_direction_available",
    "aldridge_trade_direction_method",
    "aldridge_trade_direction_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "available", "observed"}:
        return True
    if label in {"false", "no", "unavailable", "missing"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    available = _boolean(first(state, "aldridge_trade_direction_available"))
    method = normalized_status(first(state, "aldridge_trade_direction_method"))
    missing = [
        key for key, value in (
            ("aldridge_trade_direction_available", available),
            ("aldridge_trade_direction_method", method or None),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "aldridge_trade_direction_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("aldridge_trade_direction_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    actual = any(token in method for token in ("exchange buyer seller identifier", "buyer seller identifier", "actual trade side", "native trade direction"))
    inferred = any(token in method for token in ("tick rule", "quote rule", "lee ready", "lee ready rule", "bulk volume", "bvc"))
    if not available:
        assessment = "DIRECTION_UNAVAILABLE"
        reason = "the feed does not provide a trade-direction identifier"
    elif actual:
        assessment = "OBSERVED_DIRECTION"
        reason = "the feed records a native buyer/seller trade identifier"
    elif inferred:
        assessment = "INFERRED_DIRECTION_UNCERTAIN"
        reason = "trade direction is inferred from Level I/II data rather than observed directly"
    else:
        assessment = "DIRECTION_METHOD_UNRESOLVED"
        reason = "trade direction availability is claimed but its method is not recognized"
    result["aldridge_trade_direction_assessment"] = assessment
    result["aldridge_trade_direction_method"] = method
    result["warnings"] = ["inferred trade direction must not be treated as native market-order truth"] if inferred else []
    result["reasons"] = [reason]
    return result

