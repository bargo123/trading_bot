from __future__ import annotations

import pytest

from aegis.research.book_strategy_replay import (
    replay_executable_outcome,
    summarize_strategy_evidence,
)


def test_buy_uses_ask_entry_and_bid_exit_and_sell_is_reversed():
    quotes = [
        {"timestamp": 0, "bid": 100.0, "ask": 100.2},
        {"timestamp": 3, "bid": 100.5, "ask": 100.7},
    ]
    buy = replay_executable_outcome(quotes, side="BUY", horizon_s=3)
    sell = replay_executable_outcome(quotes, side="SELL", horizon_s=3)
    assert buy["gross_pnl"] == pytest.approx(0.3)
    assert sell["gross_pnl"] == pytest.approx(-0.7)
    assert buy["p_captured_win"] == 1.0
    assert sell["p_captured_win"] == 0.0


def test_costs_are_applied_once_and_horizons_are_distinct():
    quotes = [
        {"timestamp": 0, "bid": 100.0, "ask": 100.2},
        {"timestamp": 3, "bid": 100.25, "ask": 100.45},
        {"timestamp": 10, "bid": 99.9, "ask": 100.1},
    ]
    short = replay_executable_outcome(quotes, side="BUY", horizon_s=3, commission_usd=0.01)
    long = replay_executable_outcome(quotes, side="BUY", horizon_s=10, commission_usd=0.01)
    assert short["net_pnl"] != long["net_pnl"]
    assert short["costs_usd"] == pytest.approx(0.01)
    assert short["horizon_s"] == 3
    assert long["horizon_s"] == 10


def test_net_captured_win_is_not_gross_directional_movement():
    result = replay_executable_outcome(
        [{"timestamp": 0, "bid": 100.0, "ask": 100.2}, {"timestamp": 3, "bid": 100.3, "ask": 100.5}],
        side="BUY",
        horizon_s=3,
        commission_usd=0.2,
    )
    assert result["gross_pnl"] == pytest.approx(0.1)
    assert result["net_pnl"] == pytest.approx(-0.1)
    assert result["p_captured_win"] == 0.0


def test_summary_keeps_horizon_and_provenance_separate():
    summary = summarize_strategy_evidence([
        {"strategy_id": "s", "symbol": "EURUSD", "side": "BUY", "mechanism": "x", "horizon_s": 3, "net_pnl": 1.0, "predicted_probability": 0.6, "evidence_source": "synthetic_fixture"},
        {"strategy_id": "s", "symbol": "EURUSD", "side": "BUY", "mechanism": "x", "horizon_s": 10, "net_pnl": -1.0, "predicted_probability": 0.4, "evidence_source": "synthetic_fixture"},
    ])
    assert summary["sample_size"] == 2
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["by_horizon"]["3"]["win_rate"] == 1.0
    assert summary["by_horizon"]["10"]["win_rate"] == 0.0
    assert summary["provenance_counts"]["synthetic_fixture"] == 2
