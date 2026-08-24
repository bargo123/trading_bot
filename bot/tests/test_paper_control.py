"""Offline tests for paper-only execution and cost controls."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.paper_control import (
    ProcessLock,
    assert_paper_mutation_allowed,
    firehose_can_add,
    firehose_consume_bar,
    jpy_cluster_blocks,
    paper_execution_enabled,
    target_clears_costs,
)
from aegis.config import load_config


def assert_raises_runtime_error(callable_) -> None:
    try:
        callable_()
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        return


def test_live_or_unknown_port_mutation_is_always_refused():
    for port in (4001, 7496, 9999):
        assert_raises_runtime_error(
            lambda port=port: assert_paper_mutation_allowed(
                {
                    "engine": "ibkr",
                    "ib_port": port,
                    "allow_live": True,
                    "paper_trading_enabled": True,
                }
            )
        )


def test_mutation_requires_explicit_paper_enable_flag():
    assert_raises_runtime_error(
        lambda: assert_paper_mutation_allowed(
            {"engine": "ibkr", "ib_port": 4002, "allow_live": False}
        )
    )


def test_dry_run_never_enables_execution_and_real_paper_requires_both_gates():
    base = {"engine": "ibkr", "ib_port": 4002, "allow_live": False}
    assert not paper_execution_enabled({**base, "dry_run": True, "paper_trading_enabled": True})
    assert_raises_runtime_error(
        lambda: paper_execution_enabled(
            {**base, "dry_run": False, "paper_trading_enabled": False}
        )
    )
    assert paper_execution_enabled(
        {**base, "dry_run": False, "paper_trading_enabled": True}
    )


def test_three_pip_twenty_thousand_target_fails_real_cost_gate():
    ok, net = target_clears_costs(
        quantity=20_000,
        entry=1.15430,
        target=1.15460,
        commission_round_trip_usd=4.0,
        spread_bps=0.5,
        slippage_bps=0.2,
        min_expected_net_usd=1.0,
    )
    assert not ok
    assert round(net, 3) == -1.232


def test_one_mgc_ten_tick_target_clears_full_cost_model():
    ok, net = target_clears_costs(
        quantity=1,
        contract_multiplier=10,
        entry=3500.0,
        target=3501.0,
        commission_round_trip_usd=1.92,
        spread_price=0.1,
        slippage_price=0.1,
        spread_bps=0,
        slippage_bps=0,
        min_expected_net_usd=1.0,
    )
    assert ok
    assert round(net, 2) == 6.08


def test_process_lock_rejects_duplicate_runner_then_releases():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "runner.lock"
        first = ProcessLock(path)
        second = ProcessLock(path)
        first.acquire()
        assert_raises_runtime_error(second.acquire)
        first.release()
        second.acquire()
        second.release()


def test_process_lock_try_acquire_returns_false_when_held():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "runner.lock"
        first = ProcessLock(path)
        second = ProcessLock(path)
        assert first.try_acquire()
        assert not second.try_acquire()
        first.release()


def test_ib_paper_config_defaults_to_observation_only():
    cfg = load_config(ROOT / "config_ib_paper_eurusd.yaml")
    assert cfg["ib_port"] == 4002
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is False
    assert cfg["dry_run"] is True
    assert cfg["firehose_every_bar"] is False
    assert float(cfg["max_hold_seconds"]) == 0.0


def test_mt5_mutation_requires_demo_mode_and_enable_flag():
    assert_raises_runtime_error(
        lambda: assert_paper_mutation_allowed(
            {"engine": "mt5", "mode": "mt5_demo", "allow_live": False}
        )
    )
    assert_raises_runtime_error(
        lambda: assert_paper_mutation_allowed(
            {
                "engine": "mt5",
                "mode": "live",
                "allow_live": False,
                "paper_trading_enabled": True,
            }
        )
    )
    assert_paper_mutation_allowed(
        {
            "engine": "mt5",
            "mode": "mt5_demo",
            "allow_live": False,
            "paper_trading_enabled": True,
        }
    )


def test_mt5_demo_config_is_small_size_demo_only():
    cfg = load_config(ROOT / "config_mt5_demo_eurusd.yaml")
    assert cfg["engine"] == "mt5"
    assert cfg["mode"] == "mt5_demo"
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is True
    assert cfg["dry_run"] is False
    assert cfg["firehose_every_bar"] is False
    assert float(cfg["order_quantity"]) == 0.01
    assert float(cfg["risk_percent"]) == 1


def test_mt5_m1_scalp_config_is_fast_volman_demo_only():
    cfg = load_config(ROOT / "config_mt5_demo_m1_scalp.yaml")
    assert cfg["engine"] == "mt5"
    assert cfg["mode"] == "mt5_demo"
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is True
    assert cfg["firehose_every_bar"] is True
    assert float(cfg["order_quantity"]) == 0.01
    assert float(cfg["firehose_tp_pips"]) == 16
    assert float(cfg["firehose_sl_pips"]) == 8
    assert float(cfg["max_hold_seconds"]) == 45
    assert float(cfg["flatten_if_profit_usd"]) == 0.08
    assert cfg["firehose_book_filter"] is False
    assert cfg["firehose_chart_read"] is False
    assert cfg["scratch_losers"] is False
    assert float(cfg["max_spread_pips"]) == 2
    from aegis.config import configured_symbols, max_spread_for, pip_size_for

    names = configured_symbols(cfg)
    assert names == ["EURUSD"]
    assert int(cfg["max_positions"]) == 1
    assert "AUDUSD" not in names
    assert "EURGBP" not in names
    assert "GBPUSD" not in names
    assert "USDCHF" not in names
    assert pip_size_for("EURUSD", cfg) == 0.0001
    assert pip_size_for("USDJPY", cfg) == 0.01
    assert abs(max_spread_for("EURUSD", cfg) - 0.00020) < 1e-12
    assert abs(max_spread_for("USDJPY", cfg) - 0.02) < 1e-12


def test_mt5_pa_select_config_is_demo_only_and_not_firehose():
    cfg = load_config(ROOT / "config_mt5_demo_pa_select.yaml")
    assert cfg["engine"] == "mt5"
    assert cfg["mode"] == "mt5_demo"
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is True
    assert cfg["dry_run"] is False
    assert cfg["firehose_every_bar"] is False
    assert cfg["signal_mode"] == "pa_select"
    assert float(cfg["order_quantity"]) == 0.01
    assert float(cfg["risk_percent"]) == 1
    assert int(cfg["ntz_max_trades_day"]) == 3
    assert cfg["scratch_losers"] is False
    assert int(cfg["max_positions"]) == 1
    assert float(cfg["mt5_max_lots"]) == 0.10
    assert cfg["pyramid_enabled"] is False


def test_mt5_best_config_is_ensemble_demo_only():
    cfg = load_config(ROOT / "config_mt5_demo_best.yaml")
    assert cfg["engine"] == "mt5"
    assert cfg["mode"] == "mt5_demo"
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is True
    assert cfg["signal_mode"] == "ensemble"
    assert cfg["firehose_every_bar"] is False
    assert float(cfg["order_quantity"]) == 0.01
    assert int(cfg["ensemble_min_votes"]) == 2
    assert "book_optimal" in cfg["ensemble_members"]
    assert float(cfg["mt5_max_lots"]) == 0.10


def test_mt5_firehose_hw_is_demo_gated_shape():
    cfg = load_config(ROOT / "config_mt5_demo_firehose_hw.yaml")
    assert cfg["engine"] == "mt5"
    assert cfg["mode"] == "mt5_demo"
    assert cfg["allow_live"] is False
    assert cfg["intelligent_exploration_enabled"] is True
    assert float(cfg["exploration_max_risk_per_trade_usd"]) == 0.15
    assert cfg["paper_trading_enabled"] is True
    assert cfg["firehose_every_bar"] is True
    assert cfg["firehose_book_filter"] is False
    assert cfg["firehose_chart_read"] is True
    assert cfg["firehose_vpa_filter"] is True
    assert cfg["firehose_brooks_range"] is True
    assert cfg["firehose_damir_structure"] is True
    assert cfg["firehose_jansen_filter"] is True
    assert cfg["firehose_harris_jump"] is True
    assert cfg["oms_pretrade"] is True
    assert cfg["firehose_no_stack_if_red"] is False
    assert float(cfg["max_quote_age_s"]) == 5.0
    assert float(cfg["jansen_score_min"]) == 0.15
    assert float(cfg["harris_jump_atr"]) == 1.8
    assert float(cfg["firehose_tp_pips"]) == 1.0
    assert float(cfg["firehose_sl_pips"]) >= 25.0
    assert float(cfg["flatten_if_profit_usd"]) == 0.0
    assert float(cfg["lock_mfe_usd"]) == 0.03
    assert float(cfg["giveback_floor_usd"]) == 0.01
    assert float(cfg["flatten_if_profit_usd"]) <= float(cfg["lock_mfe_usd"])
    assert cfg["firehose_stack"] is True
    assert int(cfg["firehose_max_per_symbol"]) == 3
    assert str(cfg.get("position_sizing_mode") or "") != "risk"
    assert float(cfg["order_quantity"]) == 0.01
    # The drawdown circuit breaker must be ARMED. Both of these were 0, which fully
    # disables the guards (aegis/risk.py:61,65). Limits are deliberately loose so the
    # firehose keeps its throughput, but a genuine blowup has to halt it.
    assert float(cfg.get("max_daily_loss_percent") or 0) > 0.0
    assert float(cfg.get("max_total_drawdown_percent") or 0) > 0.0
    # Loose enough not to throttle a high-throughput demo.
    assert float(cfg["max_daily_loss_percent"]) >= 5.0
    assert float(cfg["max_total_drawdown_percent"]) >= 15.0
    assert int(cfg["max_positions"]) == 40
    assert int(cfg.get("no_money_reject_limit") or 0) == 3
    assert float(cfg.get("no_money_window_s") or 0) == 300
    assert float(cfg.get("execution_backoff_s") or 0) == 60
    assert cfg.get("intel_enabled") is False
    assert cfg.get("intelligent_firehose") is True
    # Per-trade economics must stay armed: a reward smaller than the invalidation
    # distance is the shape that produced WR 91.91% with PF 0.71.
    assert float(cfg["intelligent_min_payoff_ratio"]) >= 1.0
    assert float(cfg.get("intelligent_min_expected_net_usd") or 0) >= 0.0
    assert cfg.get("intelligent_edge_sizing") is True
    # Fabricated analogue evidence must never authorise a demo trade.
    assert cfg.get("intelligent_allow_synthetic_evidence") is False
    assert cfg.get("intelligent_exploration_enabled") is True
    assert int(cfg["exploration_max_positions"]) == 2
    assert int(cfg["exploration_max_positions_per_symbol"]) == 1
    assert float(cfg["exploration_max_daily_loss_usd"]) == 1.0
    assert float(cfg["exploration_max_risk_per_trade_usd"]) == 0.15
    assert int(cfg["exploration_max_trades_per_hypothesis"]) == 5
    assert int(cfg["exploration_cooldown_after_failure_s"]) == 1800
    # Future-dated ticks must be rejected, not clamped to age 0.0.
    assert float(cfg["max_quote_future_skew_s"]) > 0
    assert float(cfg.get("intel_scratch_pips") or 0) == 4
    assert cfg.get("intel_require_htf") is False
    assert cfg.get("intel_require_structure") is False
    assert cfg.get("intel_require_body") is True
    assert float(cfg.get("intel_min_er") or 0) == 0.15
    assert cfg.get("intel_mega_book") is True
    assert int(cfg.get("intel_mega_min_votes") or 0) == 3
    assert cfg.get("intel_skip_ny_open") is False
    assert cfg.get("intel_skip_rsi_ext") is True
    assert cfg.get("intel_skip_doji_against") is True
    assert cfg.get("intel_skip_stretched_doji_buy") is True
    assert cfg.get("intel_skip_barbwire_sell") is True
    assert cfg.get("intel_skip_late_buy_chase") is True
    assert cfg.get("intel_skip_wrong_edge") is False
    assert cfg.get("intel_skip_weak_adx_edge") is False
    assert cfg.get("firehose_anchor_quote") is True
    assert float(cfg.get("scratch_never_green_seconds") or 0) == 0
    assert float(cfg["max_spread_pips"]) <= 0.5
    from aegis.config import configured_symbols

    names = configured_symbols(cfg)
    assert "GBPUSD" in names


def test_jpy_cluster_blocks_only_when_cap_hit():
    held = ["EURJPY", "USDJPY", "EURUSD"]
    assert jpy_cluster_blocks(held, "AUDJPY", 2) is True
    assert jpy_cluster_blocks(held, "AUDJPY", 3) is False
    assert jpy_cluster_blocks(held, "GBPUSD", 2) is False
    assert jpy_cluster_blocks(held, "AUDJPY", 0) is False


def test_firehose_does_not_consume_bar_on_spread_skip_or_reject():
    assert firehose_consume_bar(spread_skip=True) is False
    assert firehose_consume_bar(halted=True) is False
    assert firehose_consume_bar(order_failed=True) is False
    assert firehose_consume_bar(no_signal=True) is True
    assert firehose_consume_bar(order_ok=True) is True
    assert firehose_consume_bar(order_ok=True, stack_more=True) is False


def test_firehose_can_stack_same_product_same_side():
    assert firehose_can_add(open_total=0, max_positions=40, held_sides=[], signal_side="buy") is True
    assert (
        firehose_can_add(
            open_total=0,
            max_positions=40,
            held_sides=[],
            signal_side="buy",
            last_entry_age_s=5.0,
            clip_interval_s=15.0,
        )
        is False
    )
    assert firehose_can_add(open_total=40, max_positions=40, held_sides=[], signal_side="buy") is False
    assert (
        firehose_can_add(
            open_total=1,
            max_positions=40,
            held_sides=["buy"],
            signal_side="buy",
            stack=False,
        )
        is False
    )
    assert (
        firehose_can_add(
            open_total=1,
            max_positions=40,
            held_sides=["buy"],
            signal_side="buy",
            stack=True,
            max_per_symbol=5,
        )
        is True
    )
    assert (
        firehose_can_add(
            open_total=1,
            max_positions=40,
            held_sides=["buy"],
            signal_side="sell",
            stack=True,
            max_per_symbol=5,
        )
        is False
    )
    assert (
        firehose_can_add(
            open_total=5,
            max_positions=40,
            held_sides=["buy"] * 5,
            signal_side="buy",
            stack=True,
            max_per_symbol=5,
        )
        is False
    )
    assert (
        firehose_can_add(
            open_total=1,
            max_positions=40,
            held_sides=["buy"],
            signal_side="buy",
            stack=True,
            max_per_symbol=6,
            last_entry_age_s=1.0,
            clip_interval_s=15.0,
        )
        is False
    )
    assert (
        firehose_can_add(
            open_total=1,
            max_positions=40,
            held_sides=["buy"],
            signal_side="buy",
            stack=True,
            max_per_symbol=6,
            last_entry_age_s=16.0,
            clip_interval_s=15.0,
            held_pnl=0.05,
            no_stack_if_red=True,
        )
        is True
    )
    assert (
        firehose_can_add(
            open_total=2,
            max_positions=40,
            held_sides=["buy", "buy"],
            signal_side="buy",
            stack=True,
            max_per_symbol=6,
            held_pnl=-0.12,
            no_stack_if_red=True,
        )
        is False
    )
    assert (
        firehose_can_add(
            open_total=2,
            max_positions=40,
            held_sides=["buy", "buy"],
            signal_side="buy",
            stack=True,
            max_per_symbol=6,
            held_pnl=0.0,
            no_stack_if_red=True,
        )
        is False
    )
    assert (
        firehose_can_add(
            open_total=2,
            max_positions=40,
            held_sides=["buy", "buy"],
            signal_side="buy",
            stack=True,
            max_per_symbol=6,
            held_pnl=0.05,
            no_stack_if_red=True,
        )
        is True
    )


if __name__ == "__main__":
    test_live_or_unknown_port_mutation_is_always_refused()
    test_mutation_requires_explicit_paper_enable_flag()
    test_dry_run_never_enables_execution_and_real_paper_requires_both_gates()
    test_three_pip_twenty_thousand_target_fails_real_cost_gate()
    test_process_lock_rejects_duplicate_runner_then_releases()
    test_ib_paper_config_defaults_to_observation_only()
    test_mt5_mutation_requires_demo_mode_and_enable_flag()
    test_mt5_demo_config_is_small_size_demo_only()
    test_mt5_m1_scalp_config_is_fast_volman_demo_only()
    test_mt5_pa_select_config_is_demo_only_and_not_firehose()
    test_mt5_best_config_is_ensemble_demo_only()
    test_mt5_firehose_hw_is_demo_gated_shape()
    test_jpy_cluster_blocks_only_when_cap_hit()
    test_firehose_does_not_consume_bar_on_spread_skip_or_reject()
    test_firehose_can_stack_same_product_same_side()
    print("OK")
