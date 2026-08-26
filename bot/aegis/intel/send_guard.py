"""Pure pre-send guards for the execution path (P8).

Extracted from the runner so stale-quote refresh, margin, and min-lot
pre-checks are unit-testable without an MT5 attach.
"""
from __future__ import annotations

from dataclasses import dataclass


def needs_quote_refresh(age_s: float, *, max_age_s: float) -> bool:
    """True when the decision's quote is too old to send on directly."""
    return max_age_s > 0 and float(age_s) > float(max_age_s)


@dataclass(frozen=True)
class RefreshVerdict:
    ok: bool
    reason: str


def refresh_verdict(
    *,
    new_age_s: float,
    new_spread: float,
    max_age_s: float,
    max_spread: float,
    candidate_spread_limit: float | None = None,
) -> RefreshVerdict:
    """After fetching ONE fresh tick, decide whether the candidate survives.

    The fresh quote must itself be within age limits, and the live spread must
    still clear the symbol's spread ceiling - otherwise the candidate is
    invalidated rather than sent blind.
    """
    if max_age_s > 0 and float(new_age_s) > float(max_age_s):
        return RefreshVerdict(False, "refresh_still_stale")
    spread_limit = (
        float(candidate_spread_limit)
        if candidate_spread_limit is not None
        else float(max_spread)
    )
    if spread_limit > 0 and float(new_spread) > spread_limit + 1e-12:
        reason = (
            "spread_widened_beyond_candidate_limit"
            if candidate_spread_limit is not None
            else "spread_widened_beyond_max"
        )
        return RefreshVerdict(False, reason)
    return RefreshVerdict(True, "fresh_quote_recovered")


def candidate_spread_limit(
    *,
    entry: float,
    target: float,
    slippage_price: float = 0.0,
    commission_round_trip_usd: float = 0.0,
    usd_per_price_unit: float | None = None,
) -> float:
    """Return the candidate-specific spread budget for a fresh quote.

    The executable reward must still clear measured slippage and commission.
    A missing/invalid geometry yields zero, so the refresh guard fails closed.
    """
    try:
        reward = abs(float(target) - float(entry))
        slippage = abs(float(slippage_price or 0.0))
        if reward != reward or slippage != slippage or reward <= 0:
            return 0.0
        commission = max(0.0, float(commission_round_trip_usd or 0.0))
        if commission > 0:
            if usd_per_price_unit is None or float(usd_per_price_unit) <= 0:
                return 0.0
            commission_price = commission / float(usd_per_price_unit)
        else:
            commission_price = 0.0
        return max(0.0, reward - slippage - commission_price)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return 0.0


def margin_precheck_ok(
    funds: float | None,
    est_margin: float,
    *,
    funds_buffer: float = 0.9,
) -> bool:
    """Refuse sends that would hit 10019 No money at the broker."""
    if funds is None:
        return True  # account info unavailable: defer to broker-side protection
    if float(funds) <= 0:
        return False
    return float(est_margin) <= float(funds) * float(funds_buffer)


def estimate_margin(*, price: float, lots: float, contract_size: float, leverage: float) -> float:
    lev = max(float(leverage), 1.0)
    return abs(float(price)) * abs(float(lots)) * abs(float(contract_size)) / lev


def min_lot_ok(quantity: float, volume_min: float) -> bool:
    if float(volume_min) <= 0:
        return True
    return float(quantity) + 1e-12 >= float(volume_min)
