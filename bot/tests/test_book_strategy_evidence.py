from __future__ import annotations

from aegis.research.book_strategy_evidence import (
    compact_context_event,
    evaluate_compiled_strategy,
    evaluate_strategy_evidence,
)


def test_context_snapshot_is_point_in_time_and_hashed():
    snapshot = compact_context_event({
        "timestamp": 10,
        "symbol": "EURUSD",
        "bid": 1.1,
        "ask": 1.1001,
        "future_quote": 9,
    })
    assert snapshot["symbol"] == "EURUSD"
    assert "future_quote" not in snapshot
    assert len(snapshot["context_hash"]) == 64


def test_buy_rule_requires_explicit_inputs():
    strategy = {
        "status": "CODED_EXACT",
        "side_rule": "BUY",
        "compiled_rule": {"return_1s_gte": 0.0001},
    }
    result = evaluate_compiled_strategy(strategy, {"side": "BUY"})
    assert result["status"] == "MISSING_INPUT"
    assert "return_1s" in result["missing"]


def test_explicit_rule_matches_only_when_all_predicates_hold():
    strategy = {
        "status": "CODED_EXACT",
        "side_rule": "BUY",
        "compiled_rule": {"return_1s_gte": 0.0001, "spread_max": 1.5},
    }
    result = evaluate_compiled_strategy(
        strategy,
        {"side": "BUY", "return_1s": 0.0002, "spread": 1.2},
    )
    assert result["status"] == "MATCH"
    assert result["failed_predicates"] == []


def test_proxy_strategy_cannot_emit_exact_match():
    result = evaluate_strategy_evidence(
        {"status": "FAMILY_PROXY", "strategy_family": "momentum"},
        {"side": "BUY"},
    )
    assert result["evidence_status"] == "FAMILY_PROXY"
    assert result["evaluation_status"] == "CONTEXT_ONLY"


def test_algorithm_predicates_are_the_watcher_evaluation_input():
    strategy = {
        "status": "CODED_EXACT",
        "compiled_rule": {"structure_eq": "breakdown"},
        "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
    }
    result = evaluate_compiled_strategy(strategy, {"structure": "breakout"})
    assert result["status"] == "MATCH"


def test_exact_rule_requires_declared_features_in_addition_to_compiled_predicates():
    strategy = {
        "status": "CODED_EXACT",
        "side_rule": "BUY",
        "required_features": ["moving_average", "volume"],
        "algorithm": {
            "compiled_entry_predicates": {"structure_eq": "breakout"},
        },
    }

    missing = evaluate_compiled_strategy(strategy, {"side": "BUY", "structure": "breakout"})
    assert missing["status"] == "MISSING_INPUT"
    assert set(missing["missing"]) == {"moving_average", "volume"}

    complete = evaluate_compiled_strategy(
        strategy,
        {
            "side": "BUY",
            "structure": "breakout",
            "ema_fast": 1.101,
            "ema_slow": 1.100,
            "volume_ratio": 1.4,
        },
    )
    assert complete["status"] == "MATCH"


def test_exact_volume_rule_does_not_treat_explicit_tick_proxy_as_traded_volume():
    strategy = {
        "status": "CODED_EXACT",
        "required_features": ["volume"],
        "algorithm": {"compiled_entry_predicates": {"structure_eq": "breakout"}},
    }

    context = {
        "structure": "breakout",
        "volume": 12,
        "volume_context": {"is_real_volume": False, "source": "tick_activity_proxy"},
        "volume_data_provenance": "tick_activity_proxy",
    }
    snapshot = compact_context_event(context)
    result = evaluate_strategy_evidence(strategy, context)

    assert not snapshot["volume_context"]["is_real_volume"]
    assert snapshot["volume_data_provenance"] == "tick_activity_proxy"
    assert result["status"] == "MISSING_INPUT"
    assert "volume" in result["missing"]


def test_compact_snapshot_keeps_safe_derived_features_but_not_outcomes():
    strategy = {
        "status": "CODED_EXACT",
        "compiled_rule": {
            "momentum_gt": 0.0,
            "volatility_expansion_gte": 1.2,
            "return_3s_gt": 0.0,
        },
    }
    state = {
        "side": "BUY",
        "momentum": 0.01,
        "volatility_expansion": 1.5,
        "return_3s": 0.0001,
        "mfe": 99.0,
        "captured_exit_net_pnl": 99.0,
    }

    snapshot = compact_context_event(state)
    result = evaluate_strategy_evidence(strategy, state)

    assert snapshot["momentum"] == 0.01
    assert snapshot["volatility_expansion"] == 1.5
    assert snapshot["return_3s"] == 0.0001
    assert "mfe" not in snapshot
    assert "captured_exit_net_pnl" not in snapshot
    assert result["evaluation_status"] == "MATCH"


def test_indicator_context_is_safe_for_exact_replay_and_outcomes_remain_excluded():
    snapshot = compact_context_event({
        "side": "BUY",
        "bollinger_state": "below_lower",
        "macd_histogram": 0.0002,
        "atr_state": "stable",
        "terminal_net_pnl": 100.0,
    })

    assert snapshot["bollinger_state"] == "below_lower"
    assert snapshot["macd_histogram"] == 0.0002
    assert snapshot["atr_state"] == "stable"
    assert "terminal_net_pnl" not in snapshot


def test_new_book_context_features_are_safe_but_outcomes_stay_excluded():
    snapshot = compact_context_event({
        "side": "BUY",
        "roc_5s": 0.001,
        "roc_state": "positive",
        "sar_state": "bullish",
        "elliott_wave_state": "impulse_up",
        "order_book_data_provenance": "real_depth",
        "macro_bias": "bullish",
        "sentiment_bias": "bullish",
        "forecast_price": 1.101,
        "ml_prediction": "BUY",
        "portfolio_state": "within_limit",
        "terminal_net_pnl": 100.0,
        "mfe": 50.0,
    })

    assert snapshot["roc_5s"] == 0.001
    assert snapshot["roc_state"] == "positive"
    assert snapshot["sar_state"] == "bullish"
    assert snapshot["elliott_wave_state"] == "impulse_up"
    assert snapshot["order_book_data_provenance"] == "real_depth"
    assert snapshot["macro_bias"] == "bullish"
    assert snapshot["sentiment_bias"] == "bullish"
    assert snapshot["forecast_price"] == 1.101
    assert snapshot["ml_prediction"] == "BUY"
    assert snapshot["portfolio_state"] == "within_limit"
    assert "terminal_net_pnl" not in snapshot
    assert "mfe" not in snapshot


def test_quote_pattern_context_is_safe_but_pattern_provenance_is_preserved():
    snapshot = compact_context_event({
        "side": "BUY",
        "pnf_pattern": "double_top_breakout",
        "pnf_direction": "up",
        "pnf_box_size": 0.0002,
        "pnf_reversal_boxes": 3,
        "pnf_data_provenance": "quote_point_and_figure_proxy",
        "second_entry_direction": "up",
        "second_entry_number": 2,
        "second_entry_context": "bullish_pullback",
        "second_entry_confirmation": "quote_bar_proxy_confirmed",
        "second_entry_data_provenance": "completed_quote_bar_proxy",
        "forecast_price": 1.101,
        "forecast_current_price": 1.100,
        "forecast_horizon_s": 5,
        "forecast_oos_status": "WALK_FORWARD",
        "forecast_uncertainty": 0.0002,
        "forecast_oos_n": 40,
        "forecast_data_provenance": "causal_quote_walk_forward",
        "mfe": 50.0,
    })

    assert snapshot["pnf_pattern"] == "double_top_breakout"
    assert snapshot["pnf_data_provenance"] == "quote_point_and_figure_proxy"
    assert snapshot["second_entry_number"] == 2
    assert snapshot["second_entry_data_provenance"] == "completed_quote_bar_proxy"
    assert snapshot["forecast_oos_status"] == "WALK_FORWARD"
    assert snapshot["forecast_oos_n"] == 40
    assert snapshot["forecast_data_provenance"] == "causal_quote_walk_forward"
    assert "mfe" not in snapshot
