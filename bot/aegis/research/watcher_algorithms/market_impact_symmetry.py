"""Buy/sell market-impact symmetry diagnostic for the read-only Watcher.

The HFT literature uses directional impact symmetry as a diagnostic for
whether apparent pump-and-dump economics could exist. This evaluator requires
timestamped trade-outcome estimates and only reports the symmetry state; it
never treats asymmetry as a strategy or a direction.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "market_impact_symmetry"
SOURCES = (
    "Irene Aldridge — High-Frequency Trading",
    "Jean-Philippe Bouchaud et al. — Trades, Quotes and Prices",
    "Joel Hasbrouck — Empirical Market Microstructure",
)
KEYS = (
    "impact_buy",
    "impact_sell",
    "impact_observation_n",
    "impact_symmetry_status",
    "impact_provenance",
    "impact_p_value",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _observed(value) -> bool:
    label = normalized_status(value)
    if not label or any(_has_token(label, marker) for marker in ("unknown", "missing", "unavailable", "synthetic", "proxy", "unverified", "not observed")):
        return False
    return any(_has_token(label, marker) for marker in ("timestamped trade outcomes", "observed impact", "measured impact"))


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("timestamped_buy_sell_impact_estimates",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    buy = number(first(state, "impact_buy"))
    sell = number(first(state, "impact_sell"))
    observations = number(first(state, "impact_observation_n"))
    if None in {buy, sell, observations} or observations <= 0:
        result["impact_symmetry_assessment"] = "UNKNOWN"
        result["reasons"] = ["buy/sell impact estimates require finite values and a positive observation count"]
        return result
    if not _observed(first(state, "impact_provenance")):
        result["impact_symmetry_assessment"] = "UNKNOWN"
        result["warnings"] = ["market-impact estimates lack timestamped observed provenance"]
        result["reasons"] = ["impact symmetry cannot be inferred from generic price movement"]
        return result
    status = normalized_status(first(state, "impact_symmetry_status"))
    if _has_token(status, "symmetric") and not _has_token(status, "asymmetric"):
        result["impact_symmetry_assessment"] = "SYMMETRIC"
        result["reasons"] = ["observed buy and sell impact are classified as symmetric"]
    elif _has_token(status, "asymmetric") or _has_token(status, "unequal"):
        result["impact_symmetry_assessment"] = "ASYMMETRIC"
        result["warnings"] = ["asymmetric impact is a manipulation-risk diagnostic, not a trade signal"]
        result["reasons"] = ["observed buy and sell impact are classified as asymmetric"]
    else:
        result["impact_symmetry_assessment"] = "UNKNOWN"
        result["reasons"] = ["impact symmetry status is not explicitly classified"]
    return result
