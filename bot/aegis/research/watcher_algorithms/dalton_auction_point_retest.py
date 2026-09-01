"""Market-profile auction-point support/resistance retest perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "dalton_auction_point_retest"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Peter Steidlmayer — Steidlmayer on Markets",
)
KEYS = (
    "dalton_auction_point_direction",
    "dalton_auction_point_price",
    "dalton_retest_price",
    "dalton_retest_holds",
    "dalton_retest_close_direction",
    "dalton_auction_point_violation_ticks",
    "dalton_significant_violation_ticks",
    "dalton_data_provenance",
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
    if not _provenance_ok(first(state, "dalton_data_provenance")):
        missing.append("dalton_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "dalton_auction_point_direction"))
    direction = "up" if direction in {"up", "bull", "bullish", "buy", "long"} else "down" if direction in {"down", "bear", "bearish", "sell", "short"} else None
    point = number(first(state, "dalton_auction_point_price"))
    retest = number(first(state, "dalton_retest_price"))
    violation = number(first(state, "dalton_auction_point_violation_ticks"))
    significant = number(first(state, "dalton_significant_violation_ticks"))
    close_direction = normalized_status(first(state, "dalton_retest_close_direction"))
    close_direction = "up" if close_direction in {"up", "bull", "bullish", "buy", "long"} else "down" if close_direction in {"down", "bear", "bearish", "sell", "short"} else None
    if direction is None or close_direction is None or None in {point, retest, violation, significant} or significant <= 0.0 or violation < 0.0:
        result["reasons"] = ["auction-point retest needs finite prices, violation geometry, and directional observations"]
        return result
    if not _truth(first(state, "dalton_retest_holds")):
        result["reasons"] = ["the auction point did not hold on retest"]
        return result
    if violation > significant:
        result["reasons"] = ["the auction point was violated beyond the significant-violation allowance"]
        return result
    if close_direction != direction:
        result["reasons"] = ["the retest close does not continue in the auction-point direction"]
        return result
    signal = "BUY" if direction == "up" else "SELL"
    result.update(
        {
            "dalton_auction_point_holds": True,
            "dalton_auction_point_price": point,
            "dalton_retest_price": retest,
            "dalton_violation_ticks": violation,
        }
    )
    return with_direction(result, state, signal, "auction point held on retest and the close preserved the auction direction")
