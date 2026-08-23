"""Deterministic tests for broker-native chronological replay."""
from __future__ import annotations

import pandas as pd
import pytest

from aegis.intel.broker_math import BrokerSymbolSpec
from aegis.research_factory.replay import ReplayCostEvidence, replay_hypothesis
from aegis.research_factory.rules import CompileResult


def _compiled(*, side, stop, target, max_hold_s=None, window=2, exit_type="stop_target"):
    return CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={
            "type": "breakout",
            "direction": "long" if side == "buy" else "short",
            "window": window,
        },
        exit_rule={"type": exit_type},
        required_columns=frozenset({"time", "high", "low", "close"}),
        side=side,
        invalidation_price=stop,
        target_price=target,
        max_hold_s=max_hold_s,
    )


def _breakout_frame(side):
    if side == "buy":
        prices = [
            (100.0, 100.0, 99.0),
            (100.0, 100.0, 99.0),
            (101.0, 101.0, 100.0),
            (102.5, 103.0, 100.5),
        ]
    else:
        prices = [
            (100.0, 101.0, 100.0),
            (100.0, 101.0, 100.0),
            (99.0, 100.0, 99.0),
            (97.5, 99.5, 97.0),
        ]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC"),
            "close": [price[0] for price in prices],
            "high": [price[1] for price in prices],
            "low": [price[2] for price in prices],
        }
    )


@pytest.mark.parametrize(
    "mapping",
    [
        None,
        {},
        {"trade_tick_value": 0.0, "trade_tick_size": 0.00001, "volume_min": 0.01},
        {"trade_tick_value": 1.0, "trade_tick_size": 0.0, "volume_min": 0.01},
        {"trade_tick_value": 1.0, "trade_tick_size": 0.00001, "volume_min": 0.0},
        {"trade_tick_value": True, "trade_tick_size": 0.00001, "volume_min": 0.01},
    ],
)
def test_broker_symbol_spec_rejects_missing_or_non_positive_evidence(mapping):
    with pytest.raises(ValueError):
        BrokerSymbolSpec.from_mapping(mapping)


def test_replay_without_cost_evidence_fails_closed():
    result = replay_hypothesis(pd.DataFrame(), compiled=None, costs=None)

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None
    assert result.reason == "replay cost evidence is required"


@pytest.mark.parametrize(
    "costs",
    [
        object(),
        ReplayCostEvidence(None, 1.0, 0.2, 0.0, 0.0),
        ReplayCostEvidence(object(), 1.0, 0.2, 0.0, 0.0),
        ReplayCostEvidence(BrokerSymbolSpec("bad", 1.0, 0.01), 1.0, 0.2, 0.0, 0.0),
        ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), None, 0.2, 0.0, 0.0),
        ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, "bad", 0.0, 0.0),
        ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, object(), 0.0),
        ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, None),
    ],
)
def test_malformed_replay_cost_evidence_fails_closed(costs):
    result = replay_hypothesis(
        _breakout_frame("buy"),
        _compiled(side="buy", stop=99.0, target=102.0),
        costs,
    )

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None
    assert result.reason


@pytest.mark.parametrize(
    "side,stop,target",
    [("buy", 99.0, 102.0), ("sell", 101.0, 98.0)],
)
def test_eurusd_buy_and_sell_charge_each_cost_once(side, stop, target):
    tick_value = 1.0
    lots = 2.0
    favorable_ticks = 1.0
    spread_ticks = 0.2
    slippage_ticks = 0.1
    commission_usd = 0.5
    costs = ReplayCostEvidence(
        symbol_spec=BrokerSymbolSpec(tick_value, 1.0, 0.01),
        lots=lots,
        spread_price=spread_ticks,
        commission_usd=commission_usd,
        slippage_price=slippage_ticks,
    )

    result = replay_hypothesis(
        _breakout_frame(side),
        _compiled(side=side, stop=stop, target=target),
        costs,
    )

    assert result.status == "COMPLETED"
    assert len(result.trades) == 1
    trade = result.trades[0]
    expected_gross = favorable_ticks * tick_value * lots
    expected_cost = (
        spread_ticks * tick_value * lots
        + commission_usd
        + slippage_ticks * tick_value * lots
    )
    assert trade.gross_pnl_usd == pytest.approx(expected_gross)
    assert trade.cost_usd == pytest.approx(expected_cost)
    assert trade.net_pnl_usd == pytest.approx(expected_gross - expected_cost)
    assert trade.exit_reason == "target"
    assert trade.exit_price == target


def test_usdjpy_replay_uses_broker_tick_value():
    tick_size = 0.01
    tick_value = 0.67
    lots = 0.5
    favorable_ticks = 5.0
    spread_ticks = 2.0
    slippage_ticks = 1.0
    commission_usd = 0.2
    frame = _breakout_frame("sell")
    frame[["close", "high", "low"]] = 150.0 + (
        frame[["close", "high", "low"]] - 100.0
    ) * 0.05
    costs = ReplayCostEvidence(
        symbol_spec=BrokerSymbolSpec(tick_value, tick_size, 0.01),
        lots=lots,
        spread_price=spread_ticks * tick_size,
        commission_usd=commission_usd,
        slippage_price=slippage_ticks * tick_size,
    )

    result = replay_hypothesis(
        frame,
        _compiled(side="sell", stop=150.05, target=149.90),
        costs,
    )

    trade = result.trades[0]
    expected_gross = favorable_ticks * tick_value * lots
    expected_cost = (
        spread_ticks * tick_value * lots
        + commission_usd
        + slippage_ticks * tick_value * lots
    )
    assert trade.gross_pnl_usd == pytest.approx(expected_gross)
    assert trade.cost_usd == pytest.approx(expected_cost)
    assert trade.net_pnl_usd == pytest.approx(expected_gross - expected_cost)


def test_elapsed_time_uses_utc_delta_on_irregular_timestamps():
    frame = pd.DataFrame(
        {
            "time": [
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:01:00Z",
                "2026-01-01T00:05:00Z",
            ],
            "close": [100.0, 101.0, 101.5],
            "high": [100.0, 101.0, 102.0],
            "low": [99.0, 100.0, 100.5],
        }
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(
        frame,
        _compiled(
            side="buy",
            stop=98.0,
            target=103.0,
            max_hold_s=120,
            window=1,
            exit_type="elapsed_time",
        ),
        costs,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "elapsed_time"
    assert result.trades[0].exit_time == pd.Timestamp("2026-01-01T00:05:00Z")


def test_same_bar_stop_target_collision_uses_adverse_stop():
    frame = _breakout_frame("buy")
    frame.loc[3, "low"] = 98.0
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(
        frame,
        _compiled(side="buy", stop=99.0, target=102.0),
        costs,
    )

    assert result.trades[0].exit_reason == "stop"
    assert result.trades[0].exit_price == 99.0


def test_entry_on_final_interval_is_closed_at_end_of_data():
    frame = _breakout_frame("buy").iloc[:3]
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(
        frame,
        _compiled(side="buy", stop=99.0, target=102.0),
        costs,
    )

    assert len(result.trades) == 1
    assert result.trades[0].exit_reason == "end_of_data"
    assert result.trades[0].exit_time == frame.iloc[-1]["time"]
    assert result.trades[0].exit_price == pytest.approx(100.9)


def test_stop_target_geometry_is_revalidated_against_executable_entry_fill():
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(
        _breakout_frame("buy"),
        _compiled(side="buy", stop=99.0, target=101.05),
        costs,
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.trades == ()
    assert "replay entry fill" in result.reason


def test_entry_geometry_includes_adverse_entry_slippage():
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.2)

    result = replay_hypothesis(
        _breakout_frame("buy"),
        _compiled(side="buy", stop=99.0, target=101.15),
        costs,
    )

    assert result.status == "NOT_EXECUTABLE"
    assert result.trades == ()


def test_mean_reversion_consumes_normalized_z_threshold():
    close = [100.1 if index % 2 else 99.9 for index in range(20)] + [95.0]
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=21, freq="min", tz="UTC"),
            "close": close,
            "high": [value + 0.1 for value in close],
            "low": [value - 0.1 for value in close],
            "sma_20": [100.0] * 21,
        }
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    def compiled(threshold):
        return CompileResult(
            status="EXECUTABLE",
            reason="",
            entry_rule={
                "type": "mean_reversion",
                "direction": "long",
                "z_threshold": threshold,
            },
            exit_rule={"type": "stop_target"},
            required_columns=frozenset({"time", "close", "high", "low", "sma_20"}),
            side="buy",
        )

    triggered = replay_hypothesis(frame, compiled(4.0), costs)
    filtered = replay_hypothesis(frame, compiled(5.0), costs)

    assert len(triggered.trades) == 1
    assert triggered.trades[0].entry_time == frame.iloc[-1]["time"]
    assert filtered.status == "NO_TRADES"


def test_regime_structure_entry_consumes_required_regimes_and_structure():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
            "close": [100.0, 100.1, 100.2],
            "high": [100.1, 100.2, 100.3],
            "low": [99.9, 100.0, 100.1],
            "regime": ["range", "trend", "trend"],
            "structure": ["breakout", None, "breakout"],
        }
    )
    compiled = CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={
            "type": "regime_structure_alignment",
            "direction": "long",
            "required_regimes": ["trend"],
            "required_structure": True,
        },
        exit_rule={"type": "stop_target"},
        required_columns=frozenset({"time", "regime", "structure"}),
        side="buy",
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(frame, compiled, costs)

    assert len(result.trades) == 1
    assert result.trades[0].entry_time == frame.iloc[2]["time"]


def test_regime_change_exit_uses_the_first_changed_regime():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
            "close": [100.0, 101.0, 101.5],
            "high": [100.0, 101.0, 102.0],
            "low": [99.0, 100.0, 101.0],
            "regime": ["trend", "trend", "range"],
        }
    )
    compiled = _compiled(
        side="buy",
        stop=None,
        target=None,
        window=1,
        exit_type="regime_change",
    )
    compiled = CompileResult(
        **{**compiled.__dict__, "required_columns": compiled.required_columns | {"regime"}}
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(frame, compiled, costs)

    assert result.trades[0].exit_reason == "regime_change"
    assert result.trades[0].exit_time == frame.iloc[2]["time"]


def test_bid_ask_data_supplies_spread_without_double_charge():
    frame = _breakout_frame("buy")
    frame["bid"] = frame["close"] - 0.2
    frame["ask"] = frame["close"] + 0.2
    frame["high_bid"] = frame["high"] - 0.2
    frame["low_bid"] = frame["low"] - 0.2
    frame["high_ask"] = frame["high"] + 0.2
    frame["low_ask"] = frame["low"] + 0.2
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, None, 0.5, 0.1)

    result = replay_hypothesis(
        frame,
        _compiled(side="buy", stop=99.0, target=102.0),
        costs,
    )

    trade = result.trades[0]
    assert result.status == "COMPLETED"
    assert trade.entry_price == pytest.approx(101.25)
    assert trade.exit_price == 102.0
    assert trade.gross_pnl_usd == pytest.approx(1.0)
    assert trade.cost_usd == pytest.approx(1.0)
    assert trade.net_pnl_usd == pytest.approx(0.0)


def test_bid_ask_midpoint_is_the_reference_when_close_conflicts():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
            "bid": [99.9, 100.9, 101.9],
            "ask": [100.1, 101.1, 102.1],
            "close": [500.0, 1000.0, -500.0],
            "regime": ["range", "trend", "range"],
            "structure": [None, "breakout", "breakout"],
        }
    )
    compiled = CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={
            "type": "regime_structure_alignment",
            "direction": "long",
            "required_regimes": ["trend"],
            "required_structure": True,
        },
        exit_rule={"type": "regime_change"},
        required_columns=frozenset({"time", "regime", "structure"}),
        side="buy",
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, None, 0.0, 0.0)

    result = replay_hypothesis(frame, compiled, costs)

    assert result.status == "COMPLETED"
    assert result.trades[0].gross_pnl_usd == pytest.approx(1.0)
    assert result.trades[0].net_pnl_usd == pytest.approx(0.8)


def test_bid_ask_replay_does_not_require_redundant_mid_prices():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="min", tz="UTC"),
            "bid": [100.0, 100.2],
            "ask": [100.2, 100.4],
            "regime": ["range", "trend"],
            "structure": [None, "breakout"],
        }
    )
    compiled = CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={
            "type": "regime_structure_alignment",
            "direction": "long",
            "required_regimes": ["trend"],
            "required_structure": True,
        },
        exit_rule={"type": "regime_change"},
        required_columns=frozenset({"time", "regime", "structure"}),
        side="buy",
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, None, 0.0, 0.0)

    result = replay_hypothesis(frame, compiled, costs)

    assert result.status == "COMPLETED"
    assert result.trades[0].entry_price == pytest.approx(100.4)
    assert result.trades[0].exit_reason == "end_of_data"


@pytest.mark.parametrize("field", ["close", "high", "low"])
def test_non_finite_mid_entry_observation_returns_no_evidence(field):
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="min", tz="UTC"),
            "close": [100.0, 100.2],
            "high": [100.1, 100.3],
            "low": [99.9, 100.1],
            "regime": ["range", "trend"],
            "structure": [None, "breakout"],
        }
    )
    frame.loc[1, field] = float("nan")
    compiled = CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={
            "type": "regime_structure_alignment",
            "direction": "long",
            "required_regimes": ["trend"],
            "required_structure": True,
        },
        exit_rule={"type": "regime_change"},
        required_columns=frozenset({"time", "regime", "structure"}),
        side="buy",
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(frame, compiled, costs)

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None


@pytest.mark.parametrize("field", ["close", "high", "low"])
def test_non_finite_mid_exit_observation_returns_no_evidence(field):
    frame = _breakout_frame("buy")
    frame.loc[3, field] = float("nan")
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(
        frame,
        _compiled(side="buy", stop=99.0, target=102.0),
        costs,
    )

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None


@pytest.mark.parametrize("field", ["bid", "ask", "high_bid", "low_bid"])
def test_non_finite_quote_exit_observation_returns_no_evidence(field):
    frame = _breakout_frame("buy")
    frame["bid"] = frame["close"] - 0.1
    frame["ask"] = frame["close"] + 0.1
    frame["high_bid"] = frame["high"] - 0.1
    frame["low_bid"] = frame["low"] - 0.1
    frame.loc[3, field] = float("nan")
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, None, 0.0, 0.0)

    result = replay_hypothesis(
        frame,
        _compiled(side="buy", stop=99.0, target=102.0),
        costs,
    )

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None


def test_non_finite_end_of_data_liquidation_returns_no_evidence():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
            "close": [100.0, 101.0, float("nan")],
            "high": [100.0, 101.0, 101.5],
            "low": [99.0, 100.0, 100.5],
        }
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.2, 0.0, 0.0)

    result = replay_hypothesis(
        frame,
        _compiled(side="buy", stop=None, target=None, window=1),
        costs,
    )

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None


def test_non_finite_quote_midpoint_reference_returns_no_evidence():
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="min", tz="UTC"),
            "bid": [100.0, 1e308],
            "ask": [100.2, 1e308],
            "regime": ["range", "trend"],
            "structure": [None, "breakout"],
        }
    )
    compiled = CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={
            "type": "regime_structure_alignment",
            "direction": "long",
            "required_regimes": ["trend"],
            "required_structure": True,
        },
        exit_rule={"type": "regime_change"},
        required_columns=frozenset({"time", "regime", "structure"}),
        side="buy",
    )
    costs = ReplayCostEvidence(BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, None, 0.0, 0.0)

    result = replay_hypothesis(frame, compiled, costs)

    assert result.status == "NO_EVIDENCE"
    assert result.trades == ()
    assert result.metrics is None
