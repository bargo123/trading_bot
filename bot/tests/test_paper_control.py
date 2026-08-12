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


def test_ib_paper_config_defaults_to_observation_only():
    cfg = load_config(ROOT / "config_ib_paper_eurusd.yaml")
    assert cfg["ib_port"] == 4002
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is False
    assert cfg["dry_run"] is True
    assert cfg["firehose_every_bar"] is False
    assert float(cfg["max_hold_seconds"]) == 0.0


if __name__ == "__main__":
    test_live_or_unknown_port_mutation_is_always_refused()
    test_mutation_requires_explicit_paper_enable_flag()
    test_dry_run_never_enables_execution_and_real_paper_requires_both_gates()
    test_three_pip_twenty_thousand_target_fails_real_cost_gate()
    test_process_lock_rejects_duplicate_runner_then_releases()
    test_ib_paper_config_defaults_to_observation_only()
    print("OK")
