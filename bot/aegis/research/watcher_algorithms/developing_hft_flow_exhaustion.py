"""Order-flow momentum and exhaustion perspective from a practical HFT text."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "developing_hft_flow_exhaustion"
SOURCES = ("Developing High-Frequency Trading Systems",)
KEYS = (
    "developing_hft_flow_direction",
    "developing_hft_flow_size",
    "developing_hft_flow_exhausted",
    "developing_hft_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present"}


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "developing_hft_data_provenance")):
        missing.append("developing_hft_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "developing_hft_flow_direction"))
    direction = "up" if direction in {"up", "buy", "bullish", "long"} else "down" if direction in {"down", "sell", "bearish", "short"} else None
    if direction is None:
        result["reasons"] = ["order flow has no unambiguous observed direction"]
        return with_direction(result, state, None, "flow exhaustion is a research warning without a valid direction")

    flow_size = normalized_status(first(state, "developing_hft_flow_size"))
    if _truth(first(state, "developing_hft_flow_exhausted")):
        result.update({"developing_hft_reversal_risk": True, "developing_hft_flow_state": "EXHAUSTED"})
        result["reasons"] = ["order flow is drying up; the source treats momentum exhaustion as reversal risk"]
        return with_direction(result, state, None, "flow exhaustion is a warning, not a countertrend entry")
    if flow_size not in {"large", "big"}:
        result["reasons"] = ["the directional flow is not large enough for the source momentum observation"]
        return with_direction(result, state, None, "flow size is insufficient for a directional HFT perspective")

    signal = "BUY" if direction == "up" else "SELL"
    result.update({"developing_hft_reversal_risk": False, "developing_hft_flow_state": "PERSISTENT"})
    return with_direction(result, state, signal, "large directional flow remains active without observed exhaustion")
