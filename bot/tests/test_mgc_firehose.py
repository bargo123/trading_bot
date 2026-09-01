"""Pure, hand-derived tests for the cost-gated MGC firehose."""
from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.mgc_firehose import (
    CandidateScore,
    MomentumParams,
    QuoteTick,
    RegimeFlowParams,
    SecondQuote,
    aggregate_second_quotes,
    momentum_signal,
    regime_flow_signal,
    replay_momentum,
    replay_regime_flow,
    select_candidate,
    wilson_lower_bound,
)


BASE = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)


def tick(
    offset_ms: int,
    bid: float,
    ask: float,
    *,
    bid_size: float = 2.0,
    ask_size: float = 3.0,
    last: float = 0.0,
    last_size: float = 1.0,
) -> QuoteTick:
    return QuoteTick(
        time=BASE + timedelta(milliseconds=offset_ms),
        bid=bid,
        ask=ask,
        bid_size=bid_size,
        ask_size=ask_size,
        last=last,
        last_size=last_size if last else 0.0,
        local_symbol="MGCV6",
    )


def second(
    index: int,
    bid: float,
    ask: float,
    *,
    low: float | None = None,
    high: float | None = None,
    book_imbalance: float = 0.0,
    microprice: float | None = None,
    trade_flow_imbalance: float = 0.0,
) -> SecondQuote:
    low_bid = bid if low is None else low
    high_bid = bid if high is None else high
    spread = ask - bid
    return SecondQuote(
        time=BASE + timedelta(seconds=index),
        open_mid=(bid + ask) / 2.0,
        high_mid=(high_bid + high_bid + spread) / 2.0,
        low_mid=(low_bid + low_bid + spread) / 2.0,
        close_mid=(bid + ask) / 2.0,
        close_bid=bid,
        close_ask=ask,
        high_bid=high_bid,
        low_bid=low_bid,
        high_ask=high_bid + spread,
        low_ask=low_bid + spread,
        max_spread=spread,
        quote_count=1,
        trade_count=1,
        usable=True,
        local_symbol="MGCV6",
        close_bid_size=5.0,
        close_ask_size=5.0,
        book_imbalance=book_imbalance,
        microprice=(bid + ask) / 2.0 if microprice is None else microprice,
        signed_trade_flow=trade_flow_imbalance,
        traded_volume=1.0,
        trade_flow_imbalance=trade_flow_imbalance,
    )


PARAMS = MomentumParams(
    lookback_seconds=5,
    breakout_seconds=3,
    min_efficiency=0.65,
    target_ticks=8,
    stop_ticks=6,
    max_hold_seconds=10,
    cooldown_seconds=1,
)


def test_aggregate_uses_observed_executable_sides_and_rejects_crossed_quotes():
    rows = aggregate_second_quotes(
        [
            tick(100, 3500.0, 3500.1, last=3500.1),
            tick(900, 3500.1, 3500.2, last=3500.2),
            tick(1100, 3500.3, 3500.2, last=3500.2),
        ],
        tick_size=0.1,
        max_spread_ticks=4,
    )
    assert len(rows) == 2
    assert rows[0].open_mid == 3500.05
    assert rows[0].close_bid == 3500.1
    assert rows[0].close_ask == 3500.2
    assert rows[0].quote_count == 2
    assert rows[0].trade_count == 2
    assert rows[0].usable
    assert not rows[1].usable


def test_aggregate_counts_market_events_not_repeated_polls_and_computes_flow_features():
    rows = aggregate_second_quotes(
        [
            tick(100, 3500.0, 3500.2, bid_size=2, ask_size=6, last=3500.2, last_size=2),
            tick(200, 3500.0, 3500.2, bid_size=2, ask_size=6, last=3500.2, last_size=2),
            tick(300, 3500.0, 3500.2, bid_size=9, ask_size=1, last=3500.0, last_size=1),
        ],
        tick_size=0.1,
        max_spread_ticks=4,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.quote_count == 2
    assert row.trade_count == 2
    assert row.close_bid_size == 9
    assert row.close_ask_size == 1
    assert math.isclose(row.book_imbalance, 0.8)
    assert math.isclose(row.microprice, 3500.18)
    assert row.signed_trade_flow == 1.0
    assert row.traded_volume == 3.0
    assert math.isclose(row.trade_flow_imbalance, 1 / 3)


def test_long_breakout_uses_only_completed_window_and_enters_next_record():
    prices = [3500.0, 3500.1, 3500.2, 3500.3, 3500.6, 3500.7]
    bars = [second(i, price, price + 0.1) for i, price in enumerate(prices)]
    signal = momentum_signal(bars, signal_index=4, params=PARAMS, tick_size=0.1)
    assert signal is not None
    assert signal.side == "buy"
    assert signal.signal_index == 4
    assert signal.entry_index == 5
    assert signal.entry_price == bars[5].close_ask
    assert math.isclose(signal.take_profit, 3501.6)
    assert math.isclose(signal.stop_loss, 3500.2)


def test_signal_rejects_unusable_or_zero_path_history():
    flat = [second(i, 3500.0, 3500.1) for i in range(6)]
    assert momentum_signal(flat, signal_index=4, params=PARAMS, tick_size=0.1) is None
    bad = list(flat)
    bad[3] = SecondQuote(**{**bad[3].__dict__, "usable": False})
    assert momentum_signal(bad, signal_index=4, params=PARAMS, tick_size=0.1) is None


def test_regime_flow_rejects_breakout_when_book_pressure_points_the_other_way():
    prices = [3500.0, 3500.1, 3500.2, 3500.3, 3500.6, 3500.7]
    aligned = [
        second(
            i,
            price,
            price + 0.1,
            book_imbalance=0.40,
            microprice=price + 0.08,
            trade_flow_imbalance=0.30,
        )
        for i, price in enumerate(prices)
    ]
    flow = RegimeFlowParams(
        momentum=PARAMS,
        min_book_imbalance=0.20,
        min_microprice_bias_ticks=0.20,
        min_trade_flow_imbalance=0.10,
        max_spread_ticks=2,
    )
    signal = regime_flow_signal(aligned, signal_index=4, params=flow, tick_size=0.1)
    assert signal is not None
    assert signal.regime == "directional_informed"
    assert signal.flow_score > 0

    opposed = list(aligned)
    opposed[4] = SecondQuote(
        **{
            **opposed[4].__dict__,
            "book_imbalance": -0.40,
            "microprice": opposed[4].close_mid - 0.03,
            "trade_flow_imbalance": -0.30,
        }
    )
    assert regime_flow_signal(opposed, signal_index=4, params=flow, tick_size=0.1) is None


def test_replay_charges_fixed_and_tick_costs_and_resolves_ambiguous_record_stop_first():
    prices = [3500.0, 3500.1, 3500.2, 3500.3, 3500.6, 3500.7]
    bars = [second(i, price, price + 0.1) for i, price in enumerate(prices)]
    # Entry is record 5 at ask 3500.8. Record 6 crosses both 3500.2 stop and 3501.6 target.
    bars.append(second(6, 3500.8, 3500.9, low=3500.1, high=3501.7))
    summary = replay_momentum(
        bars,
        params=PARAMS,
        quantity=1,
        multiplier=10,
        tick_size=0.1,
        fixed_round_trip_usd=1.92,
        slippage_ticks=1,
        starting_equity=100.0,
    )
    assert summary.trades == 1
    assert summary.results[0].exit_reason == "ambiguous_stop_first"
    assert summary.total_cost_usd == 2.92
    assert round(summary.net_pnl_usd, 2) == -8.92
    assert round(summary.end_equity, 2) == 91.08
    assert summary.profit_factor == 0.0


def test_regime_flow_replay_uses_the_same_pressure_gate_as_live_signals():
    prices = [3500.0, 3500.1, 3500.2, 3500.3, 3500.6, 3500.7, 3501.6]
    bars = [
        second(
            i,
            price,
            price + 0.1,
            book_imbalance=0.40,
            microprice=price + 0.08,
            trade_flow_imbalance=0.30,
        )
        for i, price in enumerate(prices)
    ]
    flow = RegimeFlowParams(
        momentum=PARAMS,
        min_book_imbalance=0.20,
        min_microprice_bias_ticks=0.20,
        min_trade_flow_imbalance=0.10,
        max_spread_ticks=2,
    )
    passing = replay_regime_flow(
        bars,
        params=flow,
        quantity=1,
        multiplier=10,
        tick_size=0.1,
        fixed_round_trip_usd=1.92,
        slippage_ticks=1,
        starting_equity=100.0,
    )
    assert passing.trades == 1
    assert passing.results[0].exit_reason == "target"
    assert round(passing.net_pnl_usd, 2) == 5.08

    opposed = list(bars)
    opposed[4] = SecondQuote(
        **{
            **opposed[4].__dict__,
            "book_imbalance": -0.40,
            "microprice": opposed[4].close_mid - 0.03,
            "trade_flow_imbalance": -0.30,
        }
    )
    rejected = replay_regime_flow(
        opposed,
        params=flow,
        quantity=1,
        multiplier=10,
        tick_size=0.1,
        fixed_round_trip_usd=1.92,
        slippage_ticks=1,
        starting_equity=100.0,
    )
    assert rejected.trades == 0


def test_selector_rejects_high_frequency_candidate_with_negative_validation_expectancy():
    winner = select_candidate(
        [
            CandidateScore("spray", 0.2, -0.1, 1.2, 0.9, 1.1, 2.0, 1200),
            CandidateScore("gated", 0.1, 0.08, 1.1, 1.08, 1.0, 2.0, 300),
        ]
    )
    assert winner is not None
    assert winner.name == "gated"


def test_selector_returns_none_when_no_candidate_passes_expectancy_and_drawdown():
    assert select_candidate(
        [CandidateScore("bad", 0.1, 0.1, 1.2, 1.2, 1.0, 5.1, 1500)]
    ) is None


def test_selector_prefers_statistically_supported_validation_win_rate_after_edge_gates():
    lower_wr = CandidateScore(
        "higher_expectancy",
        0.20,
        0.14,
        1.30,
        1.20,
        1.0,
        1.0,
        400,
        validation_wins=70,
        validation_trades=100,
    )
    higher_wr = CandidateScore(
        "higher_win_rate",
        0.12,
        0.08,
        1.20,
        1.15,
        1.0,
        1.0,
        250,
        validation_wins=80,
        validation_trades=100,
    )
    assert select_candidate([lower_wr, higher_wr]) == higher_wr
    assert round(wilson_lower_bound(29, 29) * 100, 1) == 88.3
