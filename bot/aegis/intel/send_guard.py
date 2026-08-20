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
) -> RefreshVerdict:
    """After fetching ONE fresh tick, decide whether the candidate survives.

    The fresh quote must itself be within age limits, and the live spread must
    still clear the symbol's spread ceiling - otherwise the candidate is
    invalidated rather than sent blind.
    """
    if max_age_s > 0 and float(new_age_s) > float(max_age_s):
        return RefreshVerdict(False, "refresh_still_stale")
    if max_spread > 0 and float(new_spread) > float(max_spread) + 1e-12:
        return RefreshVerdict(False, "spread_widened_beyond_max")
    return RefreshVerdict(True, "fresh_quote_recovered")


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
