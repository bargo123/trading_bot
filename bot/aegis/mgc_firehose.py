"""Pure MGC quote aggregation, micro-momentum signals, and replay.

Broker I/O deliberately lives elsewhere. This module consumes normalized quotes
and uses executable bid/ask sides so research and paper execution share rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import inf, sqrt
from typing import Iterable, Literal, Optional, Sequence


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class QuoteTick:
    time: datetime
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    last: float = 0.0
    last_size: float = 0.0
    local_symbol: str = ""


@dataclass(frozen=True)
class SecondQuote:
    time: datetime
    open_mid: float
    high_mid: float
    low_mid: float
    close_mid: float
    close_bid: float
    close_ask: float
    high_bid: float
    low_bid: float
    high_ask: float
    low_ask: float
    max_spread: float
    quote_count: int
    trade_count: int
    usable: bool
    local_symbol: str
    close_bid_size: float = 0.0
    close_ask_size: float = 0.0
    book_imbalance: float = 0.0
    microprice: float = 0.0
    signed_trade_flow: float = 0.0
    traded_volume: float = 0.0
    trade_flow_imbalance: float = 0.0


@dataclass(frozen=True)
class MomentumParams:
    lookback_seconds: int
    breakout_seconds: int
    min_efficiency: float
    target_ticks: int
    stop_ticks: int
    max_hold_seconds: int
    cooldown_seconds: int


@dataclass(frozen=True)
class MomentumSignal:
    side: Side
    signal_index: int
    entry_index: int
    entry_price: float
    take_profit: float
    stop_loss: float
    efficiency: float


@dataclass(frozen=True)
class RegimeFlowParams:
    momentum: MomentumParams
    min_book_imbalance: float = 0.0
    min_microprice_bias_ticks: float = 0.0
    min_trade_flow_imbalance: float = 0.0
    max_spread_ticks: float = 4.0


@dataclass(frozen=True)
class RegimeFlowSignal:
    side: Side
    signal_index: int
    entry_index: int
    entry_price: float
    take_profit: float
    stop_loss: float
    efficiency: float
    book_imbalance: float
    microprice_bias_ticks: float
    trade_flow_imbalance: float
    flow_score: float
    regime: str


@dataclass(frozen=True)
class ReplayTrade:
    side: Side
    signal_time: datetime
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    take_profit: float
    stop_loss: float
    gross_pnl_usd: float
    cost_usd: float
    net_pnl_usd: float
    r_multiple: float
    exit_reason: str


@dataclass(frozen=True)
class ReplaySummary:
    results: tuple[ReplayTrade, ...]
    trades: int
    trades_per_day: float
    win_rate: float
    expectancy_r: float
    net_dollars_per_trade: float
    profit_factor: float
    max_drawdown_pct: float
    start_equity: float
    end_equity: float
    net_pnl_usd: float
    total_cost_usd: float
    halt_reason: str


@dataclass(frozen=True)
class CandidateScore:
    name: str
    dev_expectancy: float
    validation_expectancy: float
    dev_profit_factor: float
    validation_profit_factor: float
    worst_session_profit_factor: float
    max_drawdown_pct: float
    trades_per_day: float
    validation_wins: int = 0
    validation_trades: int = 0


def _utc_second(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0)


def aggregate_second_quotes(
    quotes: Iterable[QuoteTick],
    *,
    tick_size: float,
    max_spread_ticks: float,
) -> list[SecondQuote]:
    """Aggregate raw quotes without discarding invalid seconds."""
    if tick_size <= 0 or max_spread_ticks < 0:
        raise ValueError("tick_size must be positive and max_spread_ticks non-negative")
    ordered = sorted(quotes, key=lambda quote: quote.time)
    groups: dict[datetime, list[QuoteTick]] = {}
    for quote in ordered:
        groups.setdefault(_utc_second(quote.time), []).append(quote)

    out: list[SecondQuote] = []
    for bucket, rows in groups.items():
        valid_prices = [row for row in rows if row.bid > 0 and row.ask > 0]
        if not valid_prices:
            continue
        event_rows: list[QuoteTick] = []
        last_signature = None
        for row in valid_prices:
            signature = (
                row.bid,
                row.ask,
                row.bid_size,
                row.ask_size,
                row.last,
                row.last_size,
            )
            if signature != last_signature:
                event_rows.append(row)
                last_signature = signature
        mids = [(row.bid + row.ask) / 2.0 for row in event_rows]
        spreads = [row.ask - row.bid for row in event_rows]
        symbols = {row.local_symbol for row in valid_prices if row.local_symbol}
        usable = (
            len(valid_prices) == len(rows)
            and all(spread >= 0 for spread in spreads)
            and max(spreads) <= tick_size * max_spread_ticks + 1e-12
            and len(symbols) <= 1
        )
        signed_flow = 0.0
        traded_volume = 0.0
        trade_count = 0
        previous_trade: Optional[tuple[float, float]] = None
        previous_last = 0.0
        for row in event_rows:
            trade = (row.last, row.last_size)
            if row.last <= 0 or row.last_size <= 0 or trade == previous_trade:
                continue
            direction = 0.0
            if row.last >= row.ask:
                direction = 1.0
            elif row.last <= row.bid:
                direction = -1.0
            elif previous_last > 0:
                direction = 1.0 if row.last > previous_last else (-1.0 if row.last < previous_last else 0.0)
            signed_flow += direction * row.last_size
            traded_volume += row.last_size
            trade_count += 1
            previous_trade = trade
            previous_last = row.last
        close = event_rows[-1]
        depth = max(0.0, close.bid_size) + max(0.0, close.ask_size)
        if depth > 0:
            book_imbalance = (max(0.0, close.bid_size) - max(0.0, close.ask_size)) / depth
            microprice = (
                close.ask * max(0.0, close.bid_size)
                + close.bid * max(0.0, close.ask_size)
            ) / depth
        else:
            book_imbalance = 0.0
            microprice = (close.bid + close.ask) / 2.0
        out.append(
            SecondQuote(
                time=bucket,
                open_mid=mids[0],
                high_mid=max(mids),
                low_mid=min(mids),
                close_mid=mids[-1],
                close_bid=close.bid,
                close_ask=close.ask,
                high_bid=max(row.bid for row in event_rows),
                low_bid=min(row.bid for row in event_rows),
                high_ask=max(row.ask for row in event_rows),
                low_ask=min(row.ask for row in event_rows),
                max_spread=max(spreads),
                quote_count=len(event_rows),
                trade_count=trade_count,
                usable=usable,
                local_symbol=next(iter(symbols), ""),
                close_bid_size=max(0.0, close.bid_size),
                close_ask_size=max(0.0, close.ask_size),
                book_imbalance=book_imbalance,
                microprice=microprice,
                signed_trade_flow=signed_flow,
                traded_volume=traded_volume,
                trade_flow_imbalance=(signed_flow / traded_volume) if traded_volume > 0 else 0.0,
            )
        )
    return out


def momentum_signal(
    records: Sequence[SecondQuote],
    *,
    signal_index: int,
    params: MomentumParams,
    tick_size: float,
) -> Optional[MomentumSignal]:
    """Return a next-record executable signal using completed records only."""
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    if params.lookback_seconds < 2 or params.breakout_seconds < 1:
        raise ValueError("lookback_seconds must be >=2 and breakout_seconds >=1")
    start = signal_index - params.lookback_seconds + 1
    breakout_start = signal_index - params.breakout_seconds
    entry_index = signal_index + 1
    if start < 0 or breakout_start < 0 or entry_index >= len(records):
        return None
    history = list(records[start : signal_index + 1])
    breakout = list(records[breakout_start:signal_index])
    entry = records[entry_index]
    if len(history) != params.lookback_seconds or len(breakout) != params.breakout_seconds:
        return None
    required = [*history, *breakout, entry]
    if not all(record.usable for record in required):
        return None
    symbol = history[-1].local_symbol
    if symbol and any(record.local_symbol and record.local_symbol != symbol for record in required):
        return None
    path = sum(
        abs(history[index].close_mid - history[index - 1].close_mid)
        for index in range(1, len(history))
    )
    if path <= 0:
        return None
    displacement = history[-1].close_mid - history[0].close_mid
    efficiency = abs(displacement) / path
    if efficiency + 1e-12 < params.min_efficiency or displacement == 0:
        return None

    current = records[signal_index]
    distance_target = params.target_ticks * tick_size
    distance_stop = params.stop_ticks * tick_size
    if displacement > 0 and current.close_ask > max(record.high_ask for record in breakout):
        price = entry.close_ask
        return MomentumSignal(
            side="buy",
            signal_index=signal_index,
            entry_index=entry_index,
            entry_price=price,
            take_profit=price + distance_target,
            stop_loss=price - distance_stop,
            efficiency=efficiency,
        )
    if displacement < 0 and current.close_bid < min(record.low_bid for record in breakout):
        price = entry.close_bid
        return MomentumSignal(
            side="sell",
            signal_index=signal_index,
            entry_index=entry_index,
            entry_price=price,
            take_profit=price - distance_target,
            stop_loss=price + distance_stop,
            efficiency=efficiency,
        )
    return None


def regime_flow_signal(
    records: Sequence[SecondQuote],
    *,
    signal_index: int,
    params: RegimeFlowParams,
    tick_size: float,
) -> Optional[RegimeFlowSignal]:
    """Gate a completed-record breakout on contemporaneous executable flow."""
    signal = momentum_signal(
        records,
        signal_index=signal_index,
        params=params.momentum,
        tick_size=tick_size,
    )
    if signal is None:
        return None
    current = records[signal_index]
    spread_ticks = current.max_spread / tick_size
    if spread_ticks > params.max_spread_ticks + 1e-12:
        return None
    direction = 1.0 if signal.side == "buy" else -1.0
    midpoint = current.close_mid
    microprice = current.microprice if current.microprice > 0 else midpoint
    microprice_bias_ticks = (microprice - midpoint) / tick_size
    aligned_book = direction * current.book_imbalance
    aligned_microprice = direction * microprice_bias_ticks
    aligned_trade_flow = direction * current.trade_flow_imbalance
    if aligned_book + 1e-12 < params.min_book_imbalance:
        return None
    if aligned_microprice + 1e-12 < params.min_microprice_bias_ticks:
        return None
    if aligned_trade_flow + 1e-12 < params.min_trade_flow_imbalance:
        return None
    return RegimeFlowSignal(
        side=signal.side,
        signal_index=signal.signal_index,
        entry_index=signal.entry_index,
        entry_price=signal.entry_price,
        take_profit=signal.take_profit,
        stop_loss=signal.stop_loss,
        efficiency=signal.efficiency,
        book_imbalance=current.book_imbalance,
        microprice_bias_ticks=microprice_bias_ticks,
        trade_flow_imbalance=current.trade_flow_imbalance,
        flow_score=aligned_book + aligned_microprice + aligned_trade_flow,
        regime="directional_informed",
    )


def _exit_for_record(
    record: SecondQuote, signal: MomentumSignal
) -> tuple[Optional[float], Optional[str]]:
    if signal.side == "buy":
        stop = record.low_bid <= signal.stop_loss
        target = record.high_bid >= signal.take_profit
    else:
        stop = record.high_ask >= signal.stop_loss
        target = record.low_ask <= signal.take_profit
    if stop and target:
        return signal.stop_loss, "ambiguous_stop_first"
    if stop:
        return signal.stop_loss, "stop"
    if target:
        return signal.take_profit, "target"
    return None, None


def replay_momentum(
    records: Sequence[SecondQuote],
    *,
    params: MomentumParams,
    quantity: float,
    multiplier: float,
    tick_size: float,
    fixed_round_trip_usd: float,
    slippage_ticks: float,
    starting_equity: float,
    _regime_params: Optional[RegimeFlowParams] = None,
) -> ReplaySummary:
    """Replay one non-overlapping position at executable-side prices."""
    if quantity <= 0 or multiplier <= 0 or starting_equity <= 0:
        raise ValueError("quantity, multiplier, and starting_equity must be positive")
    transaction_cost = max(0.0, fixed_round_trip_usd) + (
        max(0.0, slippage_ticks) * tick_size * quantity * multiplier
    )
    results: list[ReplayTrade] = []
    index = max(params.lookback_seconds - 1, params.breakout_seconds)
    while index < len(records) - 1:
        if _regime_params is None:
            signal = momentum_signal(
                records,
                signal_index=index,
                params=params,
                tick_size=tick_size,
            )
        else:
            signal = regime_flow_signal(
                records,
                signal_index=index,
                params=_regime_params,
                tick_size=tick_size,
            )
        if signal is None:
            index += 1
            continue
        exit_index: Optional[int] = None
        exit_price: Optional[float] = None
        exit_reason = ""
        for candidate_index in range(signal.entry_index + 1, len(records)):
            record = records[candidate_index]
            if not record.usable:
                exit_index = candidate_index
                exit_price = record.close_bid if signal.side == "buy" else record.close_ask
                exit_reason = "feed_invalid"
                break
            price, reason = _exit_for_record(record, signal)
            if reason is not None:
                exit_index, exit_price, exit_reason = candidate_index, price, reason
                break
            held = (record.time - records[signal.entry_index].time).total_seconds()
            if held >= params.max_hold_seconds:
                exit_index = candidate_index
                exit_price = record.close_bid if signal.side == "buy" else record.close_ask
                exit_reason = "max_hold"
                break
        if exit_index is None:
            final_index = len(records) - 1
            if final_index <= signal.entry_index:
                break
            final = records[final_index]
            exit_index = final_index
            exit_price = final.close_bid if signal.side == "buy" else final.close_ask
            exit_reason = "end_of_data"
        direction = 1.0 if signal.side == "buy" else -1.0
        gross = direction * (float(exit_price) - signal.entry_price) * quantity * multiplier
        net = gross - transaction_cost
        initial_risk = params.stop_ticks * tick_size * quantity * multiplier + transaction_cost
        results.append(
            ReplayTrade(
                side=signal.side,
                signal_time=records[signal.signal_index].time,
                entry_time=records[signal.entry_index].time,
                exit_time=records[exit_index].time,
                entry_price=signal.entry_price,
                exit_price=float(exit_price),
                take_profit=signal.take_profit,
                stop_loss=signal.stop_loss,
                gross_pnl_usd=gross,
                cost_usd=transaction_cost,
                net_pnl_usd=net,
                r_multiple=net / initial_risk,
                exit_reason=exit_reason,
            )
        )
        index = exit_index + max(1, params.cooldown_seconds + 1)

    net_values = [trade.net_pnl_usd for trade in results]
    net_total = sum(net_values)
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = inf
    else:
        profit_factor = 0.0
    equity = starting_equity
    peak = starting_equity
    max_drawdown_pct = 0.0
    for value in net_values:
        equity += value
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown_pct = max(max_drawdown_pct, (peak - equity) / peak * 100.0)
    sessions = len({record.time.date() for record in records}) or 1
    count = len(results)
    return ReplaySummary(
        results=tuple(results),
        trades=count,
        trades_per_day=count / sessions,
        win_rate=(len(wins) / count * 100.0) if count else 0.0,
        expectancy_r=(sum(trade.r_multiple for trade in results) / count) if count else 0.0,
        net_dollars_per_trade=(net_total / count) if count else 0.0,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown_pct,
        start_equity=starting_equity,
        end_equity=starting_equity + net_total,
        net_pnl_usd=net_total,
        total_cost_usd=sum(trade.cost_usd for trade in results),
        halt_reason="end_of_data",
    )


def replay_regime_flow(
    records: Sequence[SecondQuote],
    *,
    params: RegimeFlowParams,
    quantity: float,
    multiplier: float,
    tick_size: float,
    fixed_round_trip_usd: float,
    slippage_ticks: float,
    starting_equity: float,
) -> ReplaySummary:
    """Replay the exact regime-flow gate used by paper execution."""
    return replay_momentum(
        records,
        params=params.momentum,
        quantity=quantity,
        multiplier=multiplier,
        tick_size=tick_size,
        fixed_round_trip_usd=fixed_round_trip_usd,
        slippage_ticks=slippage_ticks,
        starting_equity=starting_equity,
        _regime_params=params,
    )


def wilson_lower_bound(wins: int, trials: int, z: float = 1.96) -> float:
    """Return the Wilson lower confidence bound for a Bernoulli win rate."""
    if trials <= 0:
        return 0.0
    if wins < 0 or wins > trials or z <= 0:
        raise ValueError("wins must be within trials and z must be positive")
    observed = wins / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    centre = observed + z2 / (2.0 * trials)
    margin = z * sqrt((observed * (1.0 - observed) + z2 / (4.0 * trials)) / trials)
    return max(0.0, (centre - margin) / denominator)


def select_candidate(candidates: Sequence[CandidateScore]) -> Optional[CandidateScore]:
    """Maximize supported validation WR after expectancy and drawdown gates."""
    passing = [
        candidate
        for candidate in candidates
        if candidate.dev_expectancy > 0
        and candidate.validation_expectancy > 0
        and candidate.dev_profit_factor > 1.05
        and candidate.validation_profit_factor > 1.05
        and candidate.worst_session_profit_factor >= 0.90
        and candidate.max_drawdown_pct < 5.0
    ]
    if not passing:
        return None
    return max(
        passing,
        key=lambda candidate: (
            wilson_lower_bound(candidate.validation_wins, candidate.validation_trades),
            (
                candidate.validation_wins / candidate.validation_trades
                if candidate.validation_trades > 0
                else 0.0
            ),
            min(candidate.dev_expectancy, candidate.validation_expectancy),
            candidate.trades_per_day,
        ),
    )
