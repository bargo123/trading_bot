"""Causal bid/ask execution replay for research and validation only.

This module intentionally has no broker or engine imports.  It models the
prices that a runner would actually pay and receive so research cannot use a
mid-price or a hindsight label as an execution result.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence


def _finite(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


@dataclass(frozen=True)
class ReplayQuote:
    """One causal executable quote observation."""

    timestamp: float
    bid: float
    ask: float


@dataclass(frozen=True)
class ReplayPolicy:
    """Point-in-time lifecycle and cost assumptions for one replay."""

    horizon_s: float
    stop_distance: float | None = None
    target_distance: float | None = None
    commission_round_trip_usd: float = 0.0
    slippage_price_per_side: float = 0.0
    usd_per_price_unit: float = 1.0
    entry_latency_s: float = 0.0
    close_latency_s: float = 0.0
    green_epsilon_usd: float = 0.0
    fast_winner_window_s: float = 5.0
    reject_entry: bool = False
    fill_ratio: float = 1.0

    def __post_init__(self) -> None:
        required_nonnegative = (
            "horizon_s",
            "commission_round_trip_usd",
            "slippage_price_per_side",
            "entry_latency_s",
            "close_latency_s",
            "green_epsilon_usd",
            "fast_winner_window_s",
        )
        for name in required_nonnegative:
            value = _finite(getattr(self, name))
            if value is None or value < 0.0:
                raise ValueError(f"invalid_{name}")
        unit = _finite(self.usd_per_price_unit)
        if unit is None or unit <= 0.0:
            raise ValueError("invalid_usd_per_price_unit")
        ratio = _finite(self.fill_ratio)
        if ratio is None or not 0.0 < ratio <= 1.0:
            raise ValueError("invalid_fill_ratio")
        for name in ("stop_distance", "target_distance"):
            value = getattr(self, name)
            if value is not None:
                distance = _finite(value)
                if distance is None or distance <= 0.0:
                    raise ValueError(f"invalid_{name}")


@dataclass(frozen=True)
class PendingOrderAction:
    """One causal amendment to a replayed pending order."""

    timestamp: float
    action: str
    limit_price: float | None = None


@dataclass(frozen=True)
class ReplayResult:
    """Complete, cost-aware result of one replayed lifecycle."""

    status: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    fill_status: str
    entry_timestamp: float | None = None
    exit_timestamp: float | None = None
    entry_price: float | None = None
    liquidation_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    exit_reason: str | None = None
    gross_pnl: float | None = None
    commission_usd: float | None = None
    slippage_cost_usd: float | None = None
    net_pnl: float | None = None
    mfe_net_pnl: float | None = None
    mae_net_pnl: float | None = None
    time_to_first_net_green_s: float | None = None
    never_green: bool | None = None
    green_then_loser: bool | None = None
    time_to_peak_s: float | None = None
    tail_loss_usd: float | None = None
    p_captured_win: float | None = None
    outcome: str | None = None
    pending_status: str | None = None
    reject_reason: str | None = None
    quotes_evaluated: int = 0


@dataclass(frozen=True)
class ReplayLeg:
    """One immutable basket leg for offline replay."""

    leg_id: str
    symbol: str
    side: str
    quantity: float
    quotes: Sequence[ReplayQuote]
    decision_ts: float | None = None


@dataclass(frozen=True)
class ReplayBasketResult:
    status: str
    legs: tuple[ReplayResult, ...]
    leg_ids: tuple[str, ...]
    net_pnl: float | None
    completed_legs: int


def _normalize_side(side: object) -> str:
    value = str(side or "").strip().lower()
    if value not in {"buy", "sell"}:
        raise ValueError("invalid_side")
    return value


def _validated_quotes(quotes: Iterable[ReplayQuote]) -> tuple[list[ReplayQuote], str | None]:
    normalized: list[ReplayQuote] = []
    previous_timestamp: float | None = None
    previous_identity: tuple[float, float, float] | None = None
    for raw in quotes:
        timestamp = _finite(getattr(raw, "timestamp", None))
        bid = _finite(getattr(raw, "bid", None))
        ask = _finite(getattr(raw, "ask", None))
        if (
            timestamp is None
            or bid is None
            or ask is None
            or timestamp < 0.0
            or bid <= 0.0
            or ask <= 0.0
            or ask < bid
        ):
            return [], "INVALID_QUOTE"
        identity = (timestamp, bid, ask)
        if previous_identity == identity:
            return [], "DUPLICATE_QUOTE"
        if previous_timestamp is not None and timestamp < previous_timestamp:
            return [], "OUT_OF_ORDER_QUOTE"
        item = ReplayQuote(timestamp=timestamp, bid=bid, ask=ask)
        normalized.append(item)
        previous_timestamp = timestamp
        previous_identity = identity
    if not normalized:
        return [], "NO_QUOTES"
    return normalized, None


def _empty(
    *,
    status: str,
    symbol: str,
    side: str,
    quantity: float,
    fill_status: str = "UNFILLED",
    pending_status: str | None = None,
    reject_reason: str | None = None,
    quotes_evaluated: int = 0,
) -> ReplayResult:
    return ReplayResult(
        status=status,
        symbol=str(symbol).upper(),
        side=side,
        quantity=float(quantity),
        filled_quantity=0.0,
        fill_status=fill_status,
        pending_status=pending_status,
        reject_reason=reject_reason,
        quotes_evaluated=quotes_evaluated,
    )


def _entry_price(quote: ReplayQuote, side: str, slip: float) -> tuple[float, float]:
    if side == "buy":
        return quote.ask + slip, slip
    return quote.bid - slip, slip


def _liquidation_price(quote: ReplayQuote, side: str, slip: float) -> tuple[float, float]:
    if side == "buy":
        return quote.bid - slip, slip
    return quote.ask + slip, slip


def _replay_filled_order(
    quotes: Sequence[ReplayQuote],
    *,
    symbol: str,
    side: str,
    quantity: float,
    policy: ReplayPolicy,
    entry_index: int,
    decision_ts: float,
    entry_override: float | None = None,
    pending_status: str | None = None,
) -> ReplayResult:
    fill_quote = quotes[entry_index]
    filled_quantity = float(quantity) * float(policy.fill_ratio)
    effective_entry, entry_slip = (
        (float(entry_override), 0.0)
        if entry_override is not None
        else _entry_price(fill_quote, side, float(policy.slippage_price_per_side))
    )
    direction = 1.0 if side == "buy" else -1.0
    stop_price = (
        effective_entry - policy.stop_distance
        if side == "buy" and policy.stop_distance is not None
        else effective_entry + policy.stop_distance
        if side == "sell" and policy.stop_distance is not None
        else None
    )
    target_price = (
        effective_entry + policy.target_distance
        if side == "buy" and policy.target_distance is not None
        else effective_entry - policy.target_distance
        if side == "sell" and policy.target_distance is not None
        else None
    )
    commission = float(policy.commission_round_trip_usd)
    unit = float(policy.usd_per_price_unit)
    mfe = float("-inf")
    mae = float("inf")
    time_to_green: float | None = None
    time_to_peak: float | None = None
    peak_index: int | None = None
    trigger_index: int | None = None
    exit_reason: str | None = None
    quote_count = 0
    for index in range(entry_index + 1, len(quotes)):
        quote = quotes[index]
        quote_count += 1
        liquidation, exit_slip = _liquidation_price(
            quote, side, float(policy.slippage_price_per_side)
        )
        mark_net = (
            direction
            * (liquidation - effective_entry)
            * filled_quantity
            * unit
            - commission
        )
        if mark_net > mfe:
            mfe = mark_net
            peak_index = index
            time_to_peak = max(0.0, quote.timestamp - fill_quote.timestamp)
        mae = min(mae, mark_net)
        if time_to_green is None and mark_net > float(policy.green_epsilon_usd):
            time_to_green = max(0.0, quote.timestamp - fill_quote.timestamp)

        # Stop wins ties against target: a quote that crosses both levels is
        # conservatively treated as adverse in a discrete replay.
        if stop_price is not None and (
            liquidation <= stop_price if side == "buy" else liquidation >= stop_price
        ):
            trigger_index, exit_reason = index, "STOP"
        elif target_price is not None and (
            liquidation >= target_price if side == "buy" else liquidation <= target_price
        ):
            trigger_index, exit_reason = index, "TARGET"
        elif quote.timestamp >= fill_quote.timestamp + float(policy.horizon_s):
            trigger_index, exit_reason = index, "TIMEOUT"
        if trigger_index is None:
            continue

        exit_index = trigger_index
        close_at = quotes[trigger_index].timestamp + float(policy.close_latency_s)
        while exit_index < len(quotes) and quotes[exit_index].timestamp < close_at:
            exit_index += 1
        if exit_index >= len(quotes):
            return _empty(
                status="NO_EXIT_DATA",
                symbol=str(symbol),
                side=side,
                quantity=quantity,
                fill_status=("PARTIALLY_FILLED" if policy.fill_ratio < 1.0 else "FILLED"),
                pending_status=pending_status,
                quotes_evaluated=quote_count,
            )
        exit_quote = quotes[exit_index]
        liquidation, exit_slip = _liquidation_price(
            exit_quote, side, float(policy.slippage_price_per_side)
        )
        gross = direction * (liquidation - effective_entry) * filled_quantity * unit
        slippage_cost = (entry_slip + exit_slip) * filled_quantity * unit
        net = gross - commission
        first_green_then_loser = time_to_green is not None and net <= float(policy.green_epsilon_usd)
        return ReplayResult(
            status="CLOSED",
            symbol=str(symbol).upper(),
            side=side,
            quantity=float(quantity),
            filled_quantity=filled_quantity,
            fill_status=("PARTIALLY_FILLED" if policy.fill_ratio < 1.0 else "FILLED"),
            entry_timestamp=fill_quote.timestamp,
            exit_timestamp=exit_quote.timestamp,
            entry_price=effective_entry,
            liquidation_price=liquidation,
            stop_price=stop_price,
            target_price=target_price,
            exit_reason=exit_reason,
            gross_pnl=gross,
            commission_usd=commission,
            slippage_cost_usd=slippage_cost,
            net_pnl=net,
            mfe_net_pnl=(mfe if math.isfinite(mfe) else None),
            mae_net_pnl=(mae if math.isfinite(mae) else None),
            time_to_first_net_green_s=time_to_green,
            never_green=time_to_green is None,
            green_then_loser=first_green_then_loser,
            time_to_peak_s=time_to_peak,
            tail_loss_usd=max(0.0, -net),
            p_captured_win=1.0 if net > float(policy.green_epsilon_usd) else 0.0,
            outcome=(
                "NET_WIN" if net > float(policy.green_epsilon_usd)
                else "NET_LOSS" if net < -float(policy.green_epsilon_usd)
                else "BREAKEVEN"
            ),
            pending_status=pending_status,
            quotes_evaluated=quote_count,
        )
    return _empty(
        status="NO_EXIT_DATA",
        symbol=str(symbol),
        side=side,
        quantity=quantity,
        fill_status=("PARTIALLY_FILLED" if policy.fill_ratio < 1.0 else "FILLED"),
        pending_status=pending_status,
        quotes_evaluated=quote_count,
    )


def replay_market_order(
    quotes: Iterable[ReplayQuote],
    *,
    symbol: str,
    side: str,
    quantity: float,
    decision_ts: float | None,
    policy: ReplayPolicy,
) -> ReplayResult:
    """Replay a market order from a causal quote sequence.

    The decision timestamp and pre-entry quote history are never used to
    determine the outcome.  Future quotes are consulted only after the fill,
    sequentially, using executable bid/ask prices.
    """
    normalized_side = _normalize_side(side)
    qty = _finite(quantity)
    if qty is None or qty <= 0.0:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=float(quantity or 0.0),
            reject_reason="INVALID_QUANTITY",
        )
    checked, error = _validated_quotes(quotes)
    if error:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=qty,
            reject_reason=error,
        )
    if policy.reject_entry:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=qty,
            reject_reason="BROKER_ORDER_REJECTED",
        )
    start = checked[0].timestamp if decision_ts is None else _finite(decision_ts)
    if start is None:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=qty,
            reject_reason="INVALID_DECISION_TIMESTAMP",
        )
    active_at = start + float(policy.entry_latency_s)
    entry_index = next(
        (index for index, quote in enumerate(checked) if quote.timestamp >= active_at),
        None,
    )
    if entry_index is None:
        return _empty(
            status="NO_ENTRY_DATA",
            symbol=str(symbol),
            side=normalized_side,
            quantity=qty,
            reject_reason="NO_QUOTE_AFTER_DECISION",
        )
    return _replay_filled_order(
        checked,
        symbol=str(symbol),
        side=normalized_side,
        quantity=qty,
        policy=policy,
        entry_index=entry_index,
        decision_ts=start,
    )


def replay_pending_order(
    quotes: Iterable[ReplayQuote],
    *,
    symbol: str,
    side: str,
    quantity: float,
    decision_ts: float | None,
    limit_price: float,
    expiry_s: float,
    policy: ReplayPolicy,
    actions: Iterable[PendingOrderAction] = (),
) -> ReplayResult:
    """Replay a limit order's replace/cancel/fill/expiry lifecycle causally."""
    normalized_side = _normalize_side(side)
    limit = _finite(limit_price)
    expiry = _finite(expiry_s)
    if limit is None or limit <= 0.0 or expiry is None or expiry < 0.0:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=float(quantity or 0.0),
            pending_status="REJECTED",
            reject_reason="INVALID_PENDING_ORDER",
        )
    checked, error = _validated_quotes(quotes)
    if error:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=float(quantity or 0.0),
            pending_status="REJECTED",
            reject_reason=error,
        )
    start = checked[0].timestamp if decision_ts is None else _finite(decision_ts)
    if start is None:
        return _empty(
            status="REJECTED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=float(quantity or 0.0),
            pending_status="REJECTED",
            reject_reason="INVALID_DECISION_TIMESTAMP",
        )
    normalized_actions: list[PendingOrderAction] = []
    previous_action_ts: float | None = None
    for item in actions:
        action_ts = _finite(getattr(item, "timestamp", None))
        action = str(getattr(item, "action", "") or "").strip().upper()
        replacement = _finite(getattr(item, "limit_price", None))
        invalid = (
            action_ts is None
            or action_ts < start
            or (previous_action_ts is not None and action_ts < previous_action_ts)
            or action not in {"REPLACE", "CANCEL"}
            or (action == "REPLACE" and (replacement is None or replacement <= 0.0))
        )
        if invalid:
            return _empty(
                status="REJECTED",
                symbol=str(symbol),
                side=normalized_side,
                quantity=float(quantity or 0.0),
                pending_status="REJECTED",
                reject_reason="INVALID_PENDING_ACTION",
            )
        normalized_actions.append(PendingOrderAction(action_ts, action, replacement))
        previous_action_ts = action_ts
    active_at = start + float(policy.entry_latency_s)
    expires_at = start + expiry
    action_index = 0
    active_limit = limit
    for index, quote in enumerate(checked):
        if quote.timestamp < active_at:
            continue
        if quote.timestamp > expires_at:
            break
        while (
            action_index < len(normalized_actions)
            and normalized_actions[action_index].timestamp <= quote.timestamp
        ):
            amendment = normalized_actions[action_index]
            action_index += 1
            if amendment.action == "CANCEL":
                return _empty(
                    status="CANCELLED",
                    symbol=str(symbol),
                    side=normalized_side,
                    quantity=float(quantity),
                    pending_status="CANCELLED",
                    quotes_evaluated=index + 1,
                )
            active_limit = float(amendment.limit_price)
        touched = (
            quote.ask <= active_limit
            if normalized_side == "buy"
            else quote.bid >= active_limit
        )
        if touched:
            result = _replay_filled_order(
                checked,
                symbol=str(symbol),
                side=normalized_side,
                quantity=float(quantity),
                policy=policy,
                entry_index=index,
                decision_ts=start,
                entry_override=active_limit,
                pending_status="FILLED",
            )
            return result
    if checked[-1].timestamp >= expires_at:
        return _empty(
            status="EXPIRED",
            symbol=str(symbol),
            side=normalized_side,
            quantity=float(quantity),
            pending_status="EXPIRED",
            quotes_evaluated=len(checked),
        )
    return _empty(
        status="PENDING_UNRESOLVED",
        symbol=str(symbol),
        side=normalized_side,
        quantity=float(quantity),
        pending_status="UNRESOLVED",
        quotes_evaluated=len(checked),
    )


def replay_basket(legs: Iterable[ReplayLeg], *, policy: ReplayPolicy) -> ReplayBasketResult:
    """Replay independent legs and aggregate only broker-completable outcomes."""
    results: list[ReplayResult] = []
    leg_ids: list[str] = []
    for leg in legs:
        leg_ids.append(str(leg.leg_id))
        results.append(
            replay_market_order(
                leg.quotes,
                symbol=leg.symbol,
                side=leg.side,
                quantity=leg.quantity,
                decision_ts=leg.decision_ts,
                policy=policy,
            )
        )
    completed = sum(result.status == "CLOSED" for result in results)
    if results and completed == len(results):
        status = "CLOSED"
    elif completed:
        status = "PARTIAL"
    else:
        status = "FAILED"
    pnl_values = [result.net_pnl for result in results if result.net_pnl is not None]
    return ReplayBasketResult(
        status=status,
        legs=tuple(results),
        leg_ids=tuple(leg_ids),
        net_pnl=(sum(pnl_values) if pnl_values and completed == len(results) else None),
        completed_legs=completed,
    )


__all__ = [
    "ReplayBasketResult",
    "ReplayLeg",
    "ReplayPolicy",
    "ReplayQuote",
    "ReplayResult",
    "replay_basket",
    "replay_market_order",
    "replay_pending_order",
]
