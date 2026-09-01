"""De Jong/Rindi duration-weighted quoted-spread diagnostic."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "dejong_duration_weighted_spread"
SOURCES = ("Frank de Jong and Barbara Rindi — The Microstructure of Financial Markets",)
KEYS = (
    "dejong_quote_observations",
    "dejong_duration_data_provenance",
)


def _observations(state: Mapping[str, Any]) -> tuple[list[tuple[float, float]], int]:
    raw = first(state, "dejong_quote_observations")
    if isinstance(raw, Mapping):
        raw_items: Sequence[Any] = (raw,)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        raw_items = raw
    else:
        return [], 0

    valid: list[tuple[float, float]] = []
    invalid = 0
    for item in raw_items:
        if not isinstance(item, Mapping):
            invalid += 1
            continue
        bid = number(item.get("bid"))
        ask = number(item.get("ask"))
        duration = number(item.get("duration_s", item.get("duration")))
        if (
            bid is None
            or ask is None
            or duration is None
            or bid <= 0
            or ask < bid
            or duration <= 0
        ):
            invalid += 1
            continue
        valid.append((ask - bid, duration))
    return valid, invalid


def evaluate(state):
    found = values(state, *KEYS)
    if not explicitly_observed(
        first(state, "dejong_duration_data_provenance"),
        accepted=("observed", "measured", "replay"),
    ):
        return absent(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            ["dejong_duration_data_provenance"],
        )

    observations, invalid = _observations(state)
    if not observations:
        return absent(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            ["dejong_quote_observations"],
        )

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    sample_n = len(observations)
    total_duration = math.fsum(duration for _, duration in observations)
    calendar_spread = math.fsum(spread for spread, _ in observations) / sample_n
    duration_weighted_spread = math.fsum(
        spread * duration for spread, duration in observations
    ) / total_duration
    result.update(
        {
            "dejong_quote_sample_n": sample_n,
            "dejong_calendar_time_spread": calendar_spread,
            "dejong_duration_weighted_spread": duration_weighted_spread,
            "dejong_total_observed_duration_s": total_duration,
            "dejong_invalid_quote_observation_n": invalid,
        }
    )
    tolerance = max(1e-12, abs(calendar_spread) * 1e-9)
    if duration_weighted_spread > calendar_spread + tolerance:
        result["dejong_duration_assessment"] = "DURATION_WEIGHTED_WIDER"
    elif duration_weighted_spread < calendar_spread - tolerance:
        result["dejong_duration_assessment"] = "DURATION_WEIGHTED_NARROWER"
    else:
        result["dejong_duration_assessment"] = "DURATION_WEIGHTED_STABLE"
    result["reasons"] = [
        "calendar-time and inter-quote-duration-weighted spreads were computed from observed quote intervals"
    ]
    result["warnings"] = [
        "non-directional liquidity-cost diagnostic; it cannot authorize BUY or SELL"
    ]
    if invalid:
        result["warnings"].append(f"{invalid} invalid quote observation(s) were excluded")
    return result
