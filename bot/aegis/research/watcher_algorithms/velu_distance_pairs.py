"""Velu/Hardy/Nehren distance-based normalized pairs perspective."""
from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction

ALGORITHM_ID = "velu_distance_pairs"
SOURCES = ("Raja Velu, Maxence Hardy, and Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "symbol",
    "side",
    "velu_pair_leg_a_symbol",
    "velu_pair_leg_b_symbol",
    "velu_pair_formation_a_prices",
    "velu_pair_formation_b_prices",
    "velu_pair_current_a_price",
    "velu_pair_current_b_price",
    "velu_pair_round_trip_cost",
    "velu_pair_data_provenance",
)


def _price_series(value: Any) -> list[float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    prices: list[float] = []
    for item in value:
        price = number(item)
        if price is None or price <= 0:
            return None
        prices.append(price)
    return prices


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "velu_pair_data_provenance")
    if not explicitly_observed(
        provenance,
        accepted=("observed", "measured", "historical", "replay"),
    ):
        return absent(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            ["velu_pair_data_provenance"],
        )

    missing: list[str] = []
    leg_a = first(state, "velu_pair_leg_a_symbol")
    leg_b = first(state, "velu_pair_leg_b_symbol")
    symbol = str(first(state, "symbol") or "").strip()
    candidate_side = side(state)
    if not symbol:
        missing.append("symbol")
    if not leg_a:
        missing.append("velu_pair_leg_a_symbol")
    if not leg_b:
        missing.append("velu_pair_leg_b_symbol")
    if candidate_side is None:
        missing.append("side")
    formation_a = _price_series(first(state, "velu_pair_formation_a_prices"))
    formation_b = _price_series(first(state, "velu_pair_formation_b_prices"))
    if formation_a is None:
        missing.append("velu_pair_formation_a_prices")
    if formation_b is None:
        missing.append("velu_pair_formation_b_prices")
    current_a = number(first(state, "velu_pair_current_a_price"))
    current_b = number(first(state, "velu_pair_current_b_price"))
    if current_a is None or current_a <= 0:
        missing.append("velu_pair_current_a_price")
    if current_b is None or current_b <= 0:
        missing.append("velu_pair_current_b_price")
    cost = number(first(state, "velu_pair_round_trip_cost"))
    if cost is None or cost < 0:
        missing.append("velu_pair_round_trip_cost")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    assert formation_a is not None
    assert formation_b is not None
    assert current_a is not None
    assert current_b is not None
    assert cost is not None
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = True
    result["velu_pair_leg_a_symbol"] = str(leg_a)
    result["velu_pair_leg_b_symbol"] = str(leg_b)
    if symbol not in {str(leg_a), str(leg_b)}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["directional_claim"] = False
        result["reasons"] = ["the copied state is not one of the two pair legs"]
        return result
    if len(formation_a) != len(formation_b) or len(formation_a) < 3:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["equal formation paths with at least three observations"]
        return result

    base_a = formation_a[0]
    base_b = formation_b[0]
    differences = [a / base_a - b / base_b for a, b in zip(formation_a, formation_b)]
    mean_difference = statistics.fmean(differences)
    deviation_scale = statistics.stdev(differences)
    current_difference = current_a / base_a - current_b / base_b
    deviation = current_difference - mean_difference
    threshold = 2.0 * deviation_scale
    rms_distance = math.sqrt(math.fsum(value * value for value in differences) / len(differences))
    result.update(
        {
            "velu_pair_formation_sample_n": len(differences),
            "velu_pair_rms_distance": rms_distance,
            "velu_pair_mean_difference": mean_difference,
            "velu_pair_current_difference": current_difference,
            "velu_pair_current_deviation": deviation,
            "velu_pair_entry_threshold": threshold,
            "velu_pair_round_trip_cost": cost,
            "velu_pair_cost_hurdle_passed": False,
            "velu_pair_signal": "NONE",
        }
    )
    if deviation_scale <= 0 or abs(deviation) <= threshold:
        result["velu_pair_action"] = "NO_STATISTICAL_DIVERGENCE"
        result["reasons"] = [
            "current normalized pair distance does not exceed two formation-period standard deviations"
        ]
        return result
    if cost >= 2.0 * abs(deviation):
        result["velu_pair_action"] = "COST_HURDLE_FAIL"
        result["reasons"] = [
            "round-trip cost is not smaller than the two-sided normalized convergence opportunity"
        ]
        return result

    result["velu_pair_cost_hurdle_passed"] = True
    if deviation < 0:
        pair_signal = "BUY_A_SELL_B"
        leg_a_side, leg_b_side = "BUY", "SELL"
    else:
        pair_signal = "SELL_A_BUY_B"
        leg_a_side, leg_b_side = "SELL", "BUY"
    target_side = leg_a_side if symbol == str(leg_a) else leg_b_side
    result["velu_pair_signal"] = pair_signal
    result["velu_pair_action"] = "TWO_SIGMA_DIVERGENCE_COST_COVERED"
    result["warnings"] = [
        "paired hedge is required; this perspective is not a standalone single-leg arbitrage claim"
    ]
    return with_direction(
        result,
        state,
        target_side,
        "normalized formation-path divergence exceeds two standard deviations after explicit cost hurdle",
    )
