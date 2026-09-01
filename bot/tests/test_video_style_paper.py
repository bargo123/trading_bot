from __future__ import annotations

import pandas as pd
import pytest

from aegis.research.video_style_paper import VideoStyleConfig, simulate_video_style


def _bars(rows: list[tuple[float, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close"])


def _winning_bars() -> pd.DataFrame:
    return _bars(
        [
            (0, 100.0, 100.5, 99.5, 100.0),
            (1, 100.0, 102.0, 99.5, 101.5),
            (2, 101.5, 105.0, 101.0, 104.0),
            (3, 104.0, 109.0, 103.0, 108.0),
        ]
    )


def test_simulator_enters_on_next_bar_and_scales_only_after_favorable_move():
    result = simulate_video_style(
        {"EURUSD": _winning_bars()},
        VideoStyleConfig(reward_to_risk=4.0, scale_after_r=0.5, max_layers=2),
    )

    assert result.placed_orders is False
    assert [trade.layer for trade in result.trades] == [1, 2]
    assert result.trades[0].entry_price == pytest.approx(101.5)
    assert result.trades[1].entry_price == pytest.approx(104.0)
    assert all(trade.exit_reason == "target" for trade in result.trades)
    assert result.wins == 2
    assert result.losses == 0


def test_stop_is_tighter_than_target_and_same_bar_conflict_is_fail_closed_to_stop():
    bars = _bars(
        [
            (0, 100.0, 100.5, 99.5, 100.0),
            (1, 100.0, 102.0, 99.5, 101.5),
            (2, 101.5, 107.0, 100.0, 103.0),
        ]
    )
    result = simulate_video_style(
        {"EURUSD": bars},
        VideoStyleConfig(reward_to_risk=4.0, max_layers=1),
    )

    trade = result.trades[0]
    assert trade.exit_reason == "stop"
    assert trade.net_pnl < 0
    assert abs(trade.net_pnl) < 1.0


def test_losing_position_never_receives_an_extra_layer():
    bars = _bars(
        [
            (0, 100.0, 100.5, 99.5, 100.0),
            (1, 100.0, 102.0, 99.5, 101.5),
            (2, 101.5, 102.5, 98.0, 99.6),
            (3, 99.0, 99.5, 97.0, 98.0),
        ]
    )
    result = simulate_video_style(
        {"GBPUSD": bars},
        VideoStyleConfig(reward_to_risk=4.0, max_layers=4),
    )

    assert all(trade.layer == 1 for trade in result.trades)
    assert result.trades[0].exit_reason == "stop"


def test_costs_reduce_reported_pnl():
    no_cost = simulate_video_style(
        {"EURUSD": _winning_bars()},
        VideoStyleConfig(reward_to_risk=4.0, max_layers=1),
    )
    with_cost = simulate_video_style(
        {"EURUSD": _winning_bars()},
        VideoStyleConfig(
            reward_to_risk=4.0,
            max_layers=1,
            spread_cost=0.25,
            slippage_cost=0.10,
            commission_cost=0.05,
        ),
    )

    assert with_cost.ending_equity < no_cost.ending_equity


def test_seconds_horizon_closes_position_without_waiting_for_end_of_data():
    bars = pd.DataFrame(
        [
            ("2026-01-01T00:00:00Z", 100.0, 100.5, 99.5, 100.0),
            ("2026-01-01T00:00:01Z", 100.0, 102.0, 99.5, 101.5),
            ("2026-01-01T00:00:02Z", 101.5, 101.8, 101.2, 101.6),
            ("2026-01-01T00:00:05Z", 101.6, 101.8, 101.4, 101.7),
            ("2026-01-01T00:00:10Z", 101.7, 101.9, 101.5, 101.8),
        ],
        columns=["time", "open", "high", "low", "close"],
    )

    result = simulate_video_style(
        {"EURUSD": bars},
        VideoStyleConfig(max_layers=1, max_hold_s=3),
    )

    assert result.trades[0].exit_reason == "time"
    assert result.trades[0].exit_time == "2026-01-01T00:00:05Z"


def test_all_supplied_symbols_are_simulated_without_symbol_hardcoding():
    result = simulate_video_style(
        {"EURUSD": _winning_bars(), "SILVER": _winning_bars()},
        VideoStyleConfig(reward_to_risk=4.0, max_layers=1),
    )

    assert set(result.per_symbol) == {"EURUSD", "SILVER"}
    assert {trade.symbol for trade in result.trades} == {"EURUSD", "SILVER"}


def test_empty_input_is_a_truthful_no_trade_result():
    result = simulate_video_style({}, VideoStyleConfig())

    assert result.placed_orders is False
    assert result.trades == ()
    assert result.ending_equity == pytest.approx(result.starting_equity)


def test_malformed_bars_fail_closed_instead_of_fabricating_trades():
    malformed = pd.DataFrame({"time": [0], "open": [1.0], "close": [1.0]})

    with pytest.raises(ValueError, match="required columns"):
        simulate_video_style({"EURUSD": malformed}, VideoStyleConfig())
