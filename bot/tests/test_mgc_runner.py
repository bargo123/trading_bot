"""Offline safety and serialization tests for the MGC shadow runner."""
from __future__ import annotations

import sys
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from aegis.engines.base import OrderResult
from aegis.mgc_firehose import QuoteTick, RegimeFlowSignal, ReplaySummary
from aegis.config import load_config
from run_mgc_firehose import (
    PaperRiskState,
    append_quote,
    build_order_request,
    count_second_records,
    execution_mode,
    expected_signal_net_usd,
    load_quotes,
    paper_entry_decision,
    submit_paper_signal,
)
from tune_mgc_firehose import (
    candidate_score,
    candidate_grid,
    chronological_partitions,
    load_tick_seconds,
    load_seconds,
    promotion_decision,
    sample_readiness,
)


QUOTE = QuoteTick(
    time=datetime(2026, 8, 12, 10, 0, 0, 123000, tzinfo=timezone.utc),
    bid=3500.0,
    ask=3500.1,
    bid_size=2.0,
    ask_size=3.0,
    last=3500.1,
    last_size=1.0,
    local_symbol="MGCV6",
)

SIGNAL = RegimeFlowSignal(
    side="buy",
    signal_index=4,
    entry_index=5,
    entry_price=3500.8,
    take_profit=3501.6,
    stop_loss=3500.2,
    efficiency=0.8,
    book_imbalance=0.4,
    microprice_bias_ticks=0.3,
    trade_flow_imbalance=0.2,
    flow_score=0.9,
    regime="directional_informed",
)


def base_mgc_cfg(**overrides):
    cfg = {
        "engine": "ibkr",
        "ib_port": 4002,
        "allow_live": False,
        "symbol": "MGC",
        "order_quantity": 1,
        "contract_multiplier": 10,
        "tick_size": 0.1,
        "dry_run": True,
        "paper_trading_enabled": False,
        "paper_promoted": False,
        "ib_market_data_type": 1,
    }
    cfg.update(overrides)
    return cfg


def test_unpromoted_config_can_capture_but_cannot_send_orders():
    mode = execution_mode(
        base_mgc_cfg(dry_run=False, paper_trading_enabled=True, paper_promoted=False)
    )
    assert mode.capture
    assert not mode.send_orders
    assert mode.gate_reason == "paper_promoted is false"


def test_all_three_order_gates_are_required():
    assert not execution_mode(base_mgc_cfg(paper_promoted=True)).send_orders
    assert not execution_mode(
        base_mgc_cfg(dry_run=False, paper_trading_enabled=False, paper_promoted=True)
    ).send_orders
    assert execution_mode(
        base_mgc_cfg(dry_run=False, paper_trading_enabled=True, paper_promoted=True)
    ).send_orders


def test_promoted_config_still_refuses_orders_on_delayed_market_data():
    mode = execution_mode(
        base_mgc_cfg(
            dry_run=False,
            paper_trading_enabled=True,
            paper_promoted=True,
            ib_market_data_type=3,
        )
    )
    assert not mode.send_orders
    assert mode.gate_reason == "live market data type 1 required"


def test_paper_entry_gate_requires_flat_state_and_positive_after_cost_target():
    cfg = {
        **base_mgc_cfg(
            dry_run=False,
            paper_trading_enabled=True,
            paper_promoted=True,
        ),
        "min_expected_net_usd": 1.0,
        "max_completed_trades_hour": 100,
        "max_daily_loss_usd": 250,
        "max_consecutive_losses": 5,
        "max_cost_divergence_usd": 100,
    }
    mode = execution_mode(cfg)
    flat = PaperRiskState()
    assert paper_entry_decision(
        cfg,
        mode=mode,
        feed_usable=True,
        has_signal=True,
        expected_net_usd=5.08,
        risk=flat,
    ).allowed
    blocked = paper_entry_decision(
        cfg,
        mode=mode,
        feed_usable=True,
        has_signal=True,
        expected_net_usd=5.08,
        risk=replace(flat, working_order_count=1),
    )
    assert not blocked.allowed
    assert blocked.reason == "existing MGC position or working order"


class FakePaperEngine:
    def __init__(self):
        self.requests = []

    def place_order(self, request):
        self.requests.append(request)
        return OrderResult(ok=True, broker_order_id="123", message="status=Submitted")


def test_promoted_signal_builds_one_marketable_limit_bracket_after_cost_gate():
    cfg = {
        **base_mgc_cfg(
            dry_run=False,
            paper_trading_enabled=True,
            paper_promoted=True,
        ),
        "ib_round_trip_commission_usd": 1.92,
        "slippage_ticks": 1,
        "min_expected_net_usd": 1.0,
        "max_completed_trades_hour": 100,
        "max_daily_loss_usd": 250,
        "max_consecutive_losses": 5,
        "max_cost_divergence_usd": 100,
    }
    request = build_order_request(cfg, SIGNAL)
    assert request.symbol == "MGC"
    assert request.side == "buy"
    assert request.kind == "limit"
    assert request.limit_price == 3500.8
    assert request.stop_loss == 3500.2
    assert request.take_profit == 3501.6
    assert round(expected_signal_net_usd(cfg, SIGNAL), 2) == 5.08

    engine = FakePaperEngine()
    submission = submit_paper_signal(
        engine,
        cfg,
        mode=execution_mode(cfg),
        signal=SIGNAL,
        feed_usable=True,
        risk=PaperRiskState(),
    )
    assert submission.decision.allowed
    assert submission.order_result is not None
    assert submission.order_result.ok
    assert engine.requests == [request]


def test_wrong_mgc_size_is_rejected_before_capture_or_execution():
    try:
        execution_mode(base_mgc_cfg(order_quantity=20_000))
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "one contract" in str(exc).lower()


def test_quote_json_round_trip_preserves_contract_and_executable_sides(tmp_path):
    path = tmp_path / "ticks.jsonl"
    append_quote(path, QUOTE)
    assert load_quotes(path) == [QUOTE]


def test_old_second_capture_loads_with_zeroed_flow_features(tmp_path):
    path = tmp_path / "seconds.jsonl"
    payload = {
        "time": "2026-08-12T10:00:00+00:00",
        "open_mid": 3500.05,
        "high_mid": 3500.05,
        "low_mid": 3500.05,
        "close_mid": 3500.05,
        "close_bid": 3500.0,
        "close_ask": 3500.1,
        "high_bid": 3500.0,
        "low_bid": 3500.0,
        "high_ask": 3500.1,
        "low_ask": 3500.1,
        "max_spread": 0.1,
        "quote_count": 1,
        "trade_count": 1,
        "usable": True,
        "local_symbol": "MGCV6",
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    record = load_seconds(path)[0]
    assert record.book_imbalance == 0.0
    assert record.trade_flow_imbalance == 0.0
    assert record.microprice == 0.0


def test_raw_tick_capture_rebuilds_flow_aware_second_records(tmp_path):
    path = tmp_path / "ticks.jsonl"
    append_quote(path, replace(QUOTE, bid_size=2, ask_size=6))
    append_quote(
        path,
        replace(
            QUOTE,
            time=QUOTE.time.replace(microsecond=500000),
            bid_size=9,
            ask_size=1,
            last=3500.0,
        ),
    )
    records = load_tick_seconds(path, tick_size=0.1, max_spread_ticks=4)
    assert len(records) == 1
    assert records[0].book_imbalance == 0.8
    assert round(records[0].microprice, 2) == 3500.09


def test_second_record_counter_preserves_full_capture_progress_after_restart(tmp_path):
    path = tmp_path / "seconds.jsonl"
    path.write_text(
        "{\"usable\":true}\n{\"usable\":false}\n{\"usable\":true}\n",
        encoding="utf-8",
    )
    assert count_second_records(path) == (3, 2)


def test_tuner_requires_ten_sessions_and_quarter_million_usable_records():
    readiness = sample_readiness(session_count=2, usable_records=12_000)
    assert not readiness.ready
    assert readiness.halt_reason == "collecting ten-session broker-native sample"
    assert not sample_readiness(session_count=5, usable_records=250_000).ready
    assert sample_readiness(session_count=10, usable_records=250_000).ready


def test_chronological_partition_is_six_development_two_validation_two_holdout():
    records = [
        SimpleNamespace(time=datetime(2026, 8, day, 10, tzinfo=timezone.utc))
        for day in range(1, 11)
    ]
    development, validation, holdout = chronological_partitions(records)
    assert [record.time.day for record in development] == [1, 2, 3, 4, 5, 6]
    assert [record.time.day for record in validation] == [7, 8]
    assert [record.time.day for record in holdout] == [9, 10]


def test_candidate_grid_is_cost_viable_bounded_and_tests_flow_abstention():
    candidates = candidate_grid()
    assert 25 <= len(candidates) <= 200
    assert all(candidate.momentum.breakout_seconds < candidate.momentum.lookback_seconds for candidate in candidates)
    assert all(candidate.momentum.target_ticks >= 8 for candidate in candidates)
    assert any(candidate.min_book_imbalance == 0 for candidate in candidates)
    assert any(candidate.min_book_imbalance >= 0.20 for candidate in candidates)


def test_candidate_score_maps_validation_wr_and_cost_adjusted_metrics():
    development = summary(
        trades=120,
        win_rate=70.0,
        net_per_trade=0.80,
        profit_factor=1.20,
        drawdown=1.5,
    )
    validation = summary(
        trades=100,
        win_rate=80.0,
        net_per_trade=0.50,
        profit_factor=1.15,
        drawdown=2.0,
    )
    score = candidate_score("measured", development, validation)
    assert score.validation_wins == 80
    assert score.validation_trades == 100
    assert score.validation_expectancy == validation.expectancy_r
    assert score.validation_profit_factor == 1.15


def summary(
    *,
    trades: int,
    win_rate: float,
    net_per_trade: float,
    profit_factor: float,
    drawdown: float,
) -> ReplaySummary:
    return ReplaySummary(
        results=(),
        trades=trades,
        trades_per_day=trades / 2,
        win_rate=win_rate,
        expectancy_r=0.10,
        net_dollars_per_trade=net_per_trade,
        profit_factor=profit_factor,
        max_drawdown_pct=drawdown,
        start_equity=250_000,
        end_equity=250_000 + trades * net_per_trade,
        net_pnl_usd=trades * net_per_trade,
        total_cost_usd=trades * 2.92,
        halt_reason="end_of_data",
    )


def test_holdout_promotion_requires_credible_wr_stressed_edge_and_hour_diversification():
    primary = summary(
        trades=500,
        win_rate=80.0,
        net_per_trade=1.25,
        profit_factor=1.30,
        drawdown=2.0,
    )
    stressed = summary(
        trades=500,
        win_rate=70.0,
        net_per_trade=0.20,
        profit_factor=1.05,
        drawdown=2.5,
    )
    passed = promotion_decision(primary, stressed, hourly_pnl=[30, 25, 25, 20])
    assert passed.promoted
    too_small = promotion_decision(
        replace(primary, trades=29, win_rate=100.0),
        stressed,
        hourly_pnl=[30, 25, 25, 20],
    )
    assert not too_small.promoted
    assert too_small.halt_reason == "holdout has fewer than 500 trades"


def test_mgc_shadow_config_satisfies_aegis_config_contract():
    cfg = load_config(ROOT / "config_ib_paper_mgc_shadow.yaml")
    assert cfg["symbol"] == "MGC"
    assert cfg["timeframe"] == "1s"
    assert cfg["ib_market_data_type"] == 3
    assert cfg["paper_promoted"] is False
