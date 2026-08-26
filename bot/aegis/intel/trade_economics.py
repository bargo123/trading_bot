"""Per-trade expected-net-value gate for the Intelligent Firehose.

Why this module exists
---------------------
``aegis.intel.expected_value`` scores a *population* of outcomes, and
``aegis.intel.analogue_store`` scores the *historical state*. Neither one looks at
the geometry of the trade actually about to be sent. That gap is how a system
reaches a 91.91% win rate with a 0.71 profit factor: every individual fill can sit
on a 1-pip target above a 30-pip invalidation, so the state-level expectancy looks
positive right up until the losers land.

This module closes that gap. Before FIRE, a thesis must show that *this* entry,
against *this* invalidation, toward *this* target, after *this* moment's spread and
commission, has positive expected value.

Deterministic, no LLM, and it must never import the research package - the paper
runner imports it directly.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping

# A reward smaller than the invalidation distance is the structural signature of the
# high-win-rate / negative-expectancy failure. 1.0R is a floor, not a target.
DEFAULT_MIN_PAYOFF_RATIO = 1.0
# Expected value must clear zero by a margin, not merely tie with costs.
DEFAULT_MIN_EXPECTED_NET_USD = 0.0
# Confidence level for the conservative win-probability bound.
WILSON_Z = 1.96


@dataclass(frozen=True)
class TradeEconomics:
    """Full economic description of one prospective trade."""

    acceptable: bool
    reason: str
    entry: float
    invalidation: float | None
    target: float | None
    target_source: str
    risk_price: float | None
    reward_price: float | None
    expected_win_usd: float | None
    expected_loss_usd: float | None
    cost_usd: float | None
    p_win: float | None
    p_win_source: str
    expected_net_value_usd: float | None
    payoff_ratio: float | None
    breakeven_win_rate: float | None
    usd_per_price_unit: float | None
    lots: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def journal(self) -> dict[str, Any]:
        """Compact form for the run journal - the fields that explain the decision."""
        return {
            "econ_ok": self.acceptable,
            "econ_reason": self.reason,
            "econ_entry": self.entry,
            "econ_invalidation": self.invalidation,
            "econ_target": self.target,
            "econ_target_source": self.target_source,
            "econ_expected_win_usd": self.expected_win_usd,
            "econ_expected_loss_usd": self.expected_loss_usd,
            "econ_cost_usd": self.cost_usd,
            "econ_p_win": self.p_win,
            "econ_p_win_source": self.p_win_source,
            "econ_expected_net_usd": self.expected_net_value_usd,
            "econ_payoff_ratio": self.payoff_ratio,
            "econ_breakeven_wr": self.breakeven_win_rate,
            "econ_usd_per_price_unit": self.usd_per_price_unit,
        }


def _reject(reason: str, *, entry: float, lots: float, **kwargs: Any) -> TradeEconomics:
    base: dict[str, Any] = {
        "invalidation": None,
        "target": None,
        "target_source": "none",
        "risk_price": None,
        "reward_price": None,
        "expected_win_usd": None,
        "expected_loss_usd": None,
        "cost_usd": None,
        "p_win": None,
        "p_win_source": "none",
        "expected_net_value_usd": None,
        "payoff_ratio": None,
        "breakeven_win_rate": None,
        "usd_per_price_unit": None,
    }
    base.update(kwargs)
    return TradeEconomics(acceptable=False, reason=reason, entry=float(entry), lots=float(lots), **base)


def wilson_lower_bound(*, wins: int, n: int, z: float = WILSON_Z) -> float | None:
    """Lower bound of a binomial proportion.

    A point-estimate win rate off 20 observations is not a probability worth sizing
    against. The lower bound is what the evidence actually supports, so a thin
    sample is penalised instead of being trusted.
    """
    total = int(n)
    if total <= 0:
        return None
    hits = min(max(int(wins), 0), total)
    phat = hits / total
    denominator = 1.0 + (z * z) / total
    centre = phat + (z * z) / (2.0 * total)
    margin = z * math.sqrt((phat * (1.0 - phat) / total) + (z * z) / (4.0 * total * total))
    lower = (centre - margin) / denominator
    return max(0.0, min(1.0, lower))


def usd_per_price_unit(spec: Mapping[str, Any] | None, *, lots: float) -> float | None:
    """USD change per 1.0 of quote price, for ``lots`` of this contract.

    Prefers the broker's tick_value/tick_size pair; falls back to contract_size,
    which is exact for FX quoted in the account currency and a reasonable proxy
    otherwise. Returns None when the broker gave us nothing usable - callers must
    treat that as "cannot price this trade", never as zero cost.
    """
    if not spec or lots <= 0:
        return None
    def _num(*keys: str) -> float | None:
        for key in keys:
            value = spec.get(key)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number) and number > 0:
                return number
        return None

    tick_size = _num("trade_tick_size", "point")
    tick_value = _num("trade_tick_value_loss", "trade_tick_value", "trade_tick_value_profit")
    if tick_size and tick_value:
        return (tick_value / tick_size) * float(lots)
    contract_size = _num("trade_contract_size")
    if contract_size:
        return contract_size * float(lots)
    return None


def evaluate_trade_economics(
    *,
    side: str,
    entry: float,
    invalidation: float | None,
    target: float | None,
    lots: float,
    spec: Mapping[str, Any] | None,
    spread_price: float | None,
    commission_round_trip_usd: float = 0.0,
    slippage_price: float | None = None,
    p_win: float | None = None,
    analogue_n: int = 0,
    analogue_n_losses: int = 0,
    min_payoff_ratio: float = DEFAULT_MIN_PAYOFF_RATIO,
    min_expected_net_usd: float = DEFAULT_MIN_EXPECTED_NET_USD,
) -> TradeEconomics:
    """Decide whether one prospective trade is worth its own risk and cost.

    ``invalidation`` and ``target`` are absolute structural prices. Missing or
    side-invalid geometry is rejected rather than replaced with invented prices.

    ``p_win`` is used as supplied when given; otherwise the Wilson lower bound of the
    analogue win rate is used, so a thin sample cannot masquerade as a strong edge.
    """
    lots = float(lots or 0.0)
    entry = float(entry)
    if lots <= 0:
        return _reject("no_position_size", entry=entry, lots=lots)

    resolved_side = str(side).lower()
    if resolved_side not in {"buy", "sell"}:
        return _reject("unknown_side", entry=entry, lots=lots)

    if invalidation is None:
        return _reject("no_structural_invalidation", entry=entry, lots=lots)

    invalidation = float(invalidation)
    # The invalidation must sit on the losing side of the entry, or it is not a stop.
    if resolved_side == "buy" and invalidation >= entry:
        return _reject("invalidation_not_below_entry", entry=entry, lots=lots, invalidation=invalidation)
    if resolved_side == "sell" and invalidation <= entry:
        return _reject("invalidation_not_above_entry", entry=entry, lots=lots, invalidation=invalidation)

    risk_price = abs(entry - invalidation)
    if not math.isfinite(risk_price) or risk_price <= 0:
        return _reject("no_invalidation_distance", entry=entry, lots=lots, invalidation=invalidation)

    per_unit = usd_per_price_unit(spec, lots=lots)
    if per_unit is None or per_unit <= 0:
        return _reject(
            "contract_value_unavailable", entry=entry, lots=lots, invalidation=invalidation, risk_price=risk_price
        )

    if target is None:
        return _reject(
            "no_structural_target",
            entry=entry,
            lots=lots,
            invalidation=invalidation,
            risk_price=risk_price,
        )
    resolved_target = float(target)
    forward = (
        resolved_target - entry
        if resolved_side == "buy"
        else entry - resolved_target
    )
    if not math.isfinite(forward) or forward <= 0:
        reason = "target_not_above_entry" if resolved_side == "buy" else "target_not_below_entry"
        return _reject(
            reason,
            entry=entry,
            lots=lots,
            invalidation=invalidation,
            target=resolved_target,
            target_source="structure",
            risk_price=risk_price,
        )
    target_source = "structure"

    reward_price = abs(resolved_target - entry)

    expected_loss_usd = risk_price * per_unit
    expected_win_usd = reward_price * per_unit

    spread = 0.0 if spread_price is None else abs(float(spread_price))
    if not math.isfinite(spread):
        spread = 0.0
    slippage = 0.0 if slippage_price is None else abs(float(slippage_price))
    if not math.isfinite(slippage):
        slippage = 0.0
    cost_usd = (
        (spread + slippage) * per_unit
        + max(0.0, float(commission_round_trip_usd or 0.0))
    )

    payoff_ratio = expected_win_usd / expected_loss_usd if expected_loss_usd > 0 else None

    # Win probability: prefer the caller's calibrated value, else the conservative
    # lower bound of the analogue sample.
    p_win_source = "supplied"
    resolved_p: float | None = None
    if p_win is not None:
        try:
            candidate = float(p_win)
        except (TypeError, ValueError):
            candidate = float("nan")
        if math.isfinite(candidate) and 0.0 <= candidate <= 1.0:
            resolved_p = candidate
    if resolved_p is None:
        n = int(analogue_n)
        wins = max(0, n - int(analogue_n_losses))
        resolved_p = wilson_lower_bound(wins=wins, n=n)
        p_win_source = "analogue_wilson_lower_bound"
    if resolved_p is None:
        return _reject(
            "no_win_probability_evidence",
            entry=entry,
            lots=lots,
            invalidation=invalidation,
            target=resolved_target,
            target_source=target_source,
            risk_price=risk_price,
            reward_price=reward_price,
            expected_win_usd=expected_win_usd,
            expected_loss_usd=expected_loss_usd,
            cost_usd=cost_usd,
            payoff_ratio=payoff_ratio,
            usd_per_price_unit=per_unit,
        )

    expected_net = (
        resolved_p * expected_win_usd - (1.0 - resolved_p) * expected_loss_usd - cost_usd
    )
    denominator = expected_win_usd + expected_loss_usd
    breakeven_wr = (expected_loss_usd + cost_usd) / denominator if denominator > 0 else None

    fields: dict[str, Any] = {
        "invalidation": invalidation,
        "target": resolved_target,
        "target_source": target_source,
        "risk_price": risk_price,
        "reward_price": reward_price,
        "expected_win_usd": expected_win_usd,
        "expected_loss_usd": expected_loss_usd,
        "cost_usd": cost_usd,
        "p_win": resolved_p,
        "p_win_source": p_win_source,
        "expected_net_value_usd": expected_net,
        "payoff_ratio": payoff_ratio,
        "breakeven_win_rate": breakeven_wr,
        "usd_per_price_unit": per_unit,
    }

    floor = max(float(min_payoff_ratio), 0.0)
    if payoff_ratio is not None and floor > 0 and payoff_ratio + 1e-12 < floor:
        # This is the 1-pip-target / 30-pip-stop shape. Reject on structure alone,
        # before any win-rate argument can rescue it.
        return TradeEconomics(
            acceptable=False, reason="payoff_below_floor", entry=entry, lots=lots, **fields
        )

    if expected_net <= float(min_expected_net_usd):
        return TradeEconomics(
            acceptable=False, reason="expected_net_value_not_positive", entry=entry, lots=lots, **fields
        )

    return TradeEconomics(
        acceptable=True, reason="positive_expected_net_value", entry=entry, lots=lots, **fields
    )
