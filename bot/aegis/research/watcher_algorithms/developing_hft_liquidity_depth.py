"""Observed depth/breadth liquidity perspective from a practical HFT text."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "developing_hft_liquidity_depth"
SOURCES = ("Developing High-Frequency Trading Systems",)
KEYS = (
    "developing_hft_depth_levels",
    "developing_hft_volume_per_layer",
    "developing_hft_liquidity_state",
    "developing_hft_liquidity_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return any(token in label for token in ("observed", "real", "level 2", "order book", "market depth"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "developing_hft_liquidity_provenance")):
        missing.append("developing_hft_liquidity_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    depth = number(first(state, "developing_hft_depth_levels"))
    volume = number(first(state, "developing_hft_volume_per_layer"))
    liquidity = normalized_status(first(state, "developing_hft_liquidity_state"))
    if depth is None or volume is None or depth <= 0 or volume <= 0:
        result["developing_hft_liquidity_assessment"] = "UNKNOWN"
        result["reasons"] = ["depth and volume per layer must be positive observed values"]
        return result
    if liquidity in {"deep broad", "deep", "broad", "liquid", "high liquidity"}:
        assessment = "DEEP_BROAD"
    elif liquidity in {"thin", "shallow", "illiquid", "low liquidity"}:
        assessment = "THIN"
    else:
        assessment = "UNKNOWN"
    result["developing_hft_liquidity_assessment"] = assessment
    result["developing_hft_depth_levels"] = depth
    result["developing_hft_volume_per_layer"] = volume
    result["reasons"] = [
        "liquidity is a tradeability and impact context; it cannot select a direction by itself"
    ]
    return result
