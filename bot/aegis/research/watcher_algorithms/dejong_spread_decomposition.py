"""De Jong/Rindi quoted, effective, and realized spread decomposition."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ._common import absent, base, explicitly_observed, first, number, normalized_status, values

ALGORITHM_ID = "dejong_spread_decomposition"
SOURCES = ("Frank de Jong and Barbara Rindi — The Microstructure of Financial Markets",)
KEYS = (
    "evaluation_phase",
    "dejong_trade_observations",
    "dejong_spread_data_provenance",
)


def _trade_sign(value: Any) -> float | None:
    numeric = number(value)
    if numeric in {-1.0, 1.0}:
        return numeric
    normalized = normalized_status(value)
    if normalized in {"buy", "buyer", "buy initiated", "buyer initiated", "market buy"}:
        return 1.0
    if normalized in {"sell", "seller", "sell initiated", "seller initiated", "market sell"}:
        return -1.0
    return None


def _midpoint(item: Mapping[str, Any]) -> float | None:
    midpoint = number(item.get("midpoint", item.get("mid")))
    if midpoint is not None and midpoint > 0:
        return midpoint
    bid = number(item.get("bid"))
    ask = number(item.get("ask"))
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return None
    return (bid + ask) / 2.0


def _next_midpoint(item: Mapping[str, Any]) -> float | None:
    for key in ("next_midpoint", "midpoint_next", "next_mid"):
        value = number(item.get(key))
        if value is not None and value > 0:
            return value
    return None


def _observations(state: Mapping[str, Any]) -> tuple[list[dict[str, float]], int]:
    raw = first(state, "dejong_trade_observations")
    if isinstance(raw, Mapping):
        raw_items: Sequence[Any] = (raw,)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        raw_items = raw
    else:
        return [], 0

    valid: list[dict[str, float]] = []
    invalid = 0
    for item in raw_items:
        if not isinstance(item, Mapping):
            invalid += 1
            continue
        bid = number(item.get("bid"))
        ask = number(item.get("ask"))
        trade_price = number(item.get("trade_price", item.get("transaction_price")))
        sign = _trade_sign(
            item.get(
                "trade_initiator",
                item.get("transaction_side", item.get("trade_sign")),
            )
        )
        midpoint = _midpoint(item)
        next_midpoint = _next_midpoint(item)
        if (
            bid is None
            or ask is None
            or bid <= 0
            or ask < bid
            or trade_price is None
            or trade_price <= 0
            or sign is None
            or midpoint is None
            or next_midpoint is None
        ):
            invalid += 1
            continue
        valid.append(
            {
                "quoted": ask - bid,
                "effective": 2.0 * abs(trade_price - midpoint),
                "effective_signed": 2.0 * sign * (trade_price - midpoint),
                "realized": 2.0 * sign * (trade_price - next_midpoint),
            }
        )
    return valid, invalid


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "dejong_spread_data_provenance")
    if not explicitly_observed(
        provenance,
        accepted=("observed", "measured", "replay"),
    ):
        return absent(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            ["dejong_spread_data_provenance"],
        )

    observations, invalid = _observations(state)
    if not observations:
        return absent(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            ["dejong_trade_observations"],
        )

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    phase = normalized_status(first(state, "evaluation_phase"))
    if phase not in {"post trade", "completed trade", "trade study"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = [
            "realized spread requires a completed transaction study and is not a pre-entry signal"
        ]
        return result

    sample_n = len(observations)
    quoted = math.fsum(item["quoted"] for item in observations) / sample_n
    effective = math.fsum(item["effective"] for item in observations) / sample_n
    effective_signed = math.fsum(item["effective_signed"] for item in observations) / sample_n
    realized = math.fsum(item["realized"] for item in observations) / sample_n
    result.update(
        {
            "dejong_spread_sample_n": sample_n,
            "dejong_quoted_spread": quoted,
            "dejong_effective_spread": effective,
            "dejong_effective_signed_spread": effective_signed,
            "dejong_realized_spread": realized,
            "dejong_adverse_selection_proxy": effective_signed - realized,
            "dejong_quoted_minus_realized": quoted - realized,
            "dejong_invalid_observation_n": invalid,
        }
    )
    proxy = effective_signed - realized
    tolerance = max(1e-12, abs(quoted) * 1e-9)
    if proxy > tolerance:
        assessment = "POSITIVE_ADVERSE_SELECTION_OR_INVENTORY"
    elif proxy >= -tolerance:
        assessment = "NO_POSITIVE_ADVERSE_SELECTION_PROXY"
    else:
        assessment = "REALIZED_EXCEEDS_EFFECTIVE_SAMPLE_NOISE"
    result["dejong_spread_assessment"] = assessment
    result["reasons"] = [
        "quoted, effective, and realized spreads were computed from observed transaction/quote records"
    ]
    result["warnings"] = [
        "non-directional transaction-cost diagnostic; it cannot authorize BUY or SELL"
    ]
    if sample_n < 3:
        result["warnings"].append("small observed sample; decomposition is descriptive")
    if invalid:
        result["warnings"].append(f"{invalid} invalid observation(s) were excluded")
    return result
