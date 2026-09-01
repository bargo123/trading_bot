from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "chan_strategy_type": "mean_reversion",
        "chan_exit_style": "profit_cap",
        "chan_exit_data_provenance": "observed strategy and exit records",
    }
    state.update(overrides)
    return state


def test_chan_exit_policy_matches_exit_style_to_strategy_family():
    aligned = evaluate_module("chan_exit_policy", _state())
    assert aligned["view"] == "WAIT"
    assert aligned["chan_exit_assessment"] == "MEAN_REVERSION_EXIT_ALIGNED"
    assert aligned["directional_claim"] is False

    momentum = evaluate_module(
        "chan_exit_policy",
        _state(chan_strategy_type="momentum", chan_exit_style="stop_loss"),
    )
    assert momentum["chan_exit_assessment"] == "MOMENTUM_EXIT_ALIGNED"

    mismatch = evaluate_module(
        "chan_exit_policy",
        _state(chan_strategy_type="mean_reversion", chan_exit_style="stop_loss"),
    )
    assert mismatch["view"] == "WAIT"
    assert mismatch["chan_exit_assessment"] == "MEAN_REVERSION_STOP_LOSS_WARNING"


def test_chan_exit_policy_rejects_unknown_or_unobserved_exit_definitions():
    invalid = evaluate_module(
        "chan_exit_policy",
        _state(chan_strategy_type="other"),
    )
    assert invalid["chan_exit_assessment"] == "INVALID_EXIT_POLICY"

    missing = evaluate_module("chan_exit_policy", {"symbol": "EURUSD", "side": "BUY"})
    assert missing["view"] == "MISSING_DATA"
    assert missing["applicability"] == "MISSING_DATA"
    assert missing["execution_authority"] is False
