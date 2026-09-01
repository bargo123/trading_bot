from __future__ import annotations

import pytest

from aegis.research.execution_replay import (
    PendingOrderAction,
    ReplayLeg,
    ReplayPolicy,
    ReplayQuote,
    replay_basket,
    replay_market_order,
    replay_pending_order,
)


def _q(t: float, bid: float, ask: float) -> ReplayQuote:
    return ReplayQuote(timestamp=t, bid=bid, ask=ask)


def _policy(**overrides) -> ReplayPolicy:
    values = {
        "horizon_s": 2.0,
        "commission_round_trip_usd": 0.20,
        "slippage_price_per_side": 0.0001,
        "usd_per_price_unit": 100_000.0,
    }
    values.update(overrides)
    return ReplayPolicy(**values)


def test_buy_and_sell_use_executable_bid_ask_orientation():
    buy = replay_market_order(
        [_q(0, 1.0000, 1.0002), _q(1, 1.0005, 1.0007), _q(2, 1.0010, 1.0012)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(),
    )
    sell = replay_market_order(
        [_q(0, 1.0000, 1.0002), _q(1, 0.9995, 0.9997), _q(2, 0.9990, 0.9992)],
        symbol="EURUSD",
        side="sell",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(),
    )

    assert buy.status == sell.status == "CLOSED"
    assert buy.entry_price == pytest.approx(1.0003)
    assert buy.liquidation_price == pytest.approx(1.0009)
    assert sell.entry_price == pytest.approx(0.9999)
    assert sell.liquidation_price == pytest.approx(0.9993)
    assert buy.net_pnl == pytest.approx(0.40)
    assert sell.net_pnl == pytest.approx(0.40)


def test_commission_and_slippage_are_applied_once_and_p_capture_means_net_win():
    result = replay_market_order(
        [_q(0, 1.0000, 1.0002), _q(1, 1.0010, 1.0012)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(horizon_s=1.0, commission_round_trip_usd=0.25),
    )

    # The executable bid/ask move is $0.80 at 0.01 lots. Two one-sided
    # slippage charges remove $0.20, and the round-trip commission removes
    # $0.25 exactly once.
    assert result.gross_pnl == pytest.approx(0.60)
    assert result.slippage_cost_usd == pytest.approx(0.20)
    assert result.commission_usd == pytest.approx(0.25)
    assert result.net_pnl == pytest.approx(0.35)
    assert result.p_captured_win == pytest.approx(1.0)
    assert result.outcome == "NET_WIN"


def test_replay_records_time_to_green_mfe_mae_and_green_then_loser():
    result = replay_market_order(
        [
            _q(0, 1.0000, 1.0002),
            _q(1, 1.0008, 1.0010),
            _q(2, 0.9997, 0.9999),
            _q(3, 0.9998, 1.0000),
        ],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(horizon_s=3.0, commission_round_trip_usd=0.20),
    )

    assert result.time_to_first_net_green_s == pytest.approx(1.0)
    assert result.never_green is False
    assert result.green_then_loser is True
    assert result.mfe_net_pnl > 0
    assert result.mae_net_pnl < 0
    assert result.p_captured_win == pytest.approx(0.0)
    assert result.outcome == "NET_LOSS"


def test_stop_target_are_sequential_and_entry_rejection_is_explicit():
    stopped = replay_market_order(
        [_q(0, 1.0000, 1.0002), _q(0.1, 0.9990, 0.9992), _q(1, 1.0008, 1.0010)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(
            horizon_s=5.0,
            stop_distance=0.0005,
            target_distance=0.0005,
            commission_round_trip_usd=0.0,
            slippage_price_per_side=0.0,
        ),
    )
    rejected = replay_market_order(
        [_q(0, 1.0, 1.0002)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(reject_entry=True),
    )

    assert stopped.exit_reason == "STOP"
    assert stopped.status == "CLOSED"
    assert rejected.status == "REJECTED"
    assert rejected.reject_reason == "BROKER_ORDER_REJECTED"
    assert rejected.net_pnl is None


def test_pending_limit_can_fill_or_expire_without_lookahead_in_decision_state():
    quotes = [
        _q(0, 1.0000, 1.0002),
        _q(1, 0.9995, 0.9997),
        _q(2, 0.9990, 0.9992),
        _q(3, 0.9988, 0.9990),
    ]
    filled = replay_pending_order(
        quotes,
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        limit_price=0.9998,
        expiry_s=2.0,
        policy=_policy(horizon_s=1.0, commission_round_trip_usd=0.0, slippage_price_per_side=0.0),
    )
    expired = replay_pending_order(
        quotes[:1] + [_q(1, 1.0000, 1.0002)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        limit_price=0.9998,
        expiry_s=1.0,
        policy=_policy(),
    )

    assert filled.pending_status == "FILLED"
    assert filled.entry_price == pytest.approx(0.9998)
    assert filled.status == "CLOSED"
    assert expired.pending_status == "EXPIRED"
    assert expired.status == "EXPIRED"
    assert expired.net_pnl is None


def test_pending_limit_can_be_replaced_then_fill_at_the_revised_price():
    result = replay_pending_order(
        [
            _q(0, 1.0000, 1.0002),
            _q(1, 0.9998, 1.0000),
            _q(2, 0.9995, 0.9997),
            _q(3, 1.0000, 1.0002),
        ],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        limit_price=0.9990,
        expiry_s=5.0,
        actions=(PendingOrderAction(timestamp=1.5, action="REPLACE", limit_price=0.9998),),
        policy=_policy(
            horizon_s=1.0,
            commission_round_trip_usd=0.0,
            slippage_price_per_side=0.0,
        ),
    )

    assert result.pending_status == "FILLED"
    assert result.entry_price == pytest.approx(0.9998)
    assert result.exit_timestamp == pytest.approx(3.0)


def test_pending_limit_cancellation_wins_before_a_later_touch():
    result = replay_pending_order(
        [_q(0, 1.0000, 1.0002), _q(1, 0.9995, 0.9997)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        limit_price=0.9998,
        expiry_s=5.0,
        actions=(PendingOrderAction(timestamp=0.5, action="CANCEL"),),
        policy=_policy(),
    )

    assert result.status == "CANCELLED"
    assert result.pending_status == "CANCELLED"
    assert result.net_pnl is None


def test_basket_replay_aggregates_legs_and_preserves_leg_identity():
    result = replay_basket(
        [
            ReplayLeg(
                leg_id="leg-buy",
                symbol="EURUSD",
                side="buy",
                quantity=0.01,
                quotes=(_q(0, 1.0000, 1.0002), _q(1, 1.0010, 1.0012)),
            ),
            ReplayLeg(
                leg_id="leg-sell",
                symbol="GBPUSD",
                side="sell",
                quantity=0.01,
                quotes=(_q(0, 1.2000, 1.2002), _q(1, 1.1990, 1.1992)),
            ),
        ],
        policy=_policy(horizon_s=1.0, commission_round_trip_usd=0.0, slippage_price_per_side=0.0),
    )

    assert result.status == "CLOSED"
    assert result.leg_ids == ("leg-buy", "leg-sell")
    assert result.completed_legs == 2
    assert result.net_pnl == pytest.approx(1.6)


def test_four_leg_burst_replay_preserves_every_leg_and_total_net_pnl():
    legs = [
        ReplayLeg(
            leg_id=f"leg-{index}",
            symbol="EURUSD",
            side="buy",
            quantity=0.01,
            quotes=(_q(0, 1.0000, 1.0002), _q(1, 1.0010, 1.0012)),
        )
        for index in range(1, 5)
    ]

    result = replay_basket(
        legs,
        policy=_policy(
            horizon_s=1.0,
            commission_round_trip_usd=0.0,
            slippage_price_per_side=0.0,
        ),
    )

    assert result.status == "CLOSED"
    assert result.leg_ids == ("leg-1", "leg-2", "leg-3", "leg-4")
    assert result.completed_legs == 4
    assert result.net_pnl == pytest.approx(3.2)


def test_partial_fill_and_causal_quote_quarantine_are_explicit():
    partial = replay_market_order(
        [_q(0, 1.0000, 1.0002), _q(1, 1.0010, 1.0012)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(
            horizon_s=1.0,
            commission_round_trip_usd=0.0,
            slippage_price_per_side=0.0,
            fill_ratio=0.5,
        ),
    )
    out_of_order = replay_market_order(
        [_q(1, 1.0, 1.0002), _q(0, 1.0, 1.0002)],
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=0,
        policy=_policy(),
    )

    assert partial.fill_status == "PARTIALLY_FILLED"
    assert partial.filled_quantity == pytest.approx(0.005)
    assert partial.net_pnl == pytest.approx(0.4)
    assert out_of_order.status == "REJECTED"
    assert out_of_order.reject_reason == "OUT_OF_ORDER_QUOTE"
