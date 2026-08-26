"""Focused tests for the optional short-horizon Firehose entry gate."""
from __future__ import annotations

from aegis.intel.firehose_brain import (
    exploration_may_probe_shadow_only_model,
    _prediction_for_candidate,
    short_horizon_gate,
)


def test_short_horizon_gate_requires_calibrated_non_abstaining_prediction():
    ok, reason = short_horizon_gate(None)
    assert ok is False
    assert reason == "short_horizon_prediction_missing"

    ok, reason = short_horizon_gate(
        {"calibration_status": "not_calibrated", "abstain": False, "probability": 0.9}
    )
    assert ok is False
    assert reason == "short_horizon_not_calibrated"

    ok, reason = short_horizon_gate(
        {"calibration_status": "calibrated", "abstain": True, "probability": 0.9}
    )
    assert ok is False
    assert reason == "short_horizon_abstain"


def test_short_horizon_gate_requires_probability_and_positive_expected_value():
    base = {"calibration_status": "calibrated", "abstain": False}
    ok, reason = short_horizon_gate({**base, "probability": 0.55, "expected_net_pnl": -0.01})
    assert ok is False
    assert reason == "short_horizon_negative_expected_value"

    ok, reason = short_horizon_gate({**base, "probability": 0.75, "expected_net_pnl": 0.01})
    assert ok is True
    assert reason == "short_horizon_eligible"


def test_short_horizon_gate_rejects_negative_oos_lower_bound_when_available():
    base = {
        "calibration_status": "calibrated",
        "abstain": False,
        "probability": 0.75,
        "expected_net_pnl": 0.02,
    }

    ok, reason = short_horizon_gate({**base, "expected_net_pnl_lcb95": -0.001})
    assert ok is False
    assert reason == "short_horizon_negative_expected_value_lcb95"

    ok, reason = short_horizon_gate({**base, "expected_net_pnl_lcb95": 0.001})
    assert ok is True
    assert reason == "short_horizon_eligible"


def test_short_horizon_gate_uses_artifact_threshold_when_not_overridden():
    ok, reason = short_horizon_gate(
        {
            "calibration_status": "calibrated",
            "abstain": False,
            "probability": 0.30,
            "threshold": 0.25,
            "expected_net_pnl": 0.01,
        },
        min_probability=None,
    )

    assert ok is True
    assert reason == "short_horizon_eligible"


def test_demo_exploration_may_probe_only_shadow_only_artifact():
    cfg = {
        "mode": "mt5_demo",
        "allow_live": False,
        "paper_trading_enabled": True,
        "intelligent_exploration_enabled": True,
    }
    shadow_only = {
        "calibration_status": "unavailable",
        "abstain": True,
        "abstain_reason": "artifact_shadow_only",
        "probability": 0.0,
        "expected_net_pnl": 0.0,
    }

    assert exploration_may_probe_shadow_only_model(
        cfg, shadow_only, "short_horizon_not_calibrated"
    ) is True

    for gate_reason in (
        "short_horizon_probability_below_threshold",
        "short_horizon_negative_prediction",
        "short_horizon_negative_expected_value",
        "short_horizon_negative_expected_value_lcb95",
    ):
        assert exploration_may_probe_shadow_only_model(cfg, shadow_only, gate_reason) is False

    for abstain_reason in (
        "artifact_unavailable",
        "symbol_not_authorized",
        "quote_history_missing",
        "quote_history_insufficient",
    ):
        prediction = {**shadow_only, "abstain_reason": abstain_reason}
        assert exploration_may_probe_shadow_only_model(
            cfg, prediction, "short_horizon_not_calibrated"
        ) is False


def test_shadow_only_exploration_override_is_demo_only():
    prediction = {
        "calibration_status": "unavailable",
        "abstain": True,
        "abstain_reason": "artifact_shadow_only",
    }
    safe_cfg = {
        "mode": "mt5_demo",
        "allow_live": False,
        "paper_trading_enabled": True,
        "intelligent_exploration_enabled": True,
    }

    assert exploration_may_probe_shadow_only_model(
        safe_cfg, prediction, "short_horizon_not_calibrated"
    ) is True
    assert exploration_may_probe_shadow_only_model(
        {**safe_cfg, "allow_live": True}, prediction, "short_horizon_not_calibrated"
    ) is False
    assert exploration_may_probe_shadow_only_model(
        {**safe_cfg, "mode": "live"}, prediction, "short_horizon_not_calibrated"
    ) is False
    assert exploration_may_probe_shadow_only_model(
        {**safe_cfg, "paper_trading_enabled": False}, prediction, "short_horizon_not_calibrated"
    ) is False
    assert exploration_may_probe_shadow_only_model(
        {**safe_cfg, "intelligent_exploration_enabled": False}, prediction,
        "short_horizon_not_calibrated"
    ) is False


def test_candidate_prediction_uses_its_own_side_and_horizon():
    prediction = {
        "selected_side": "buy",
        "side_predictions": {
            "buy": {"by_horizon": {
                "3": {"probability": 0.61, "expected_net_pnl": 0.03},
                "20": {"probability": 0.42, "expected_net_pnl": -0.02},
            }},
            "sell": {"by_horizon": {
                "3": {"probability": 0.58, "expected_net_pnl": 0.01},
            }},
        },
    }

    fast = _prediction_for_candidate(prediction, side="buy", horizon_s=3)
    slow = _prediction_for_candidate(prediction, side="buy", horizon_s=20)
    other_side = _prediction_for_candidate(prediction, side="sell", horizon_s=3)

    assert fast["expected_net_pnl"] == 0.03
    assert slow["expected_net_pnl"] == -0.02
    assert other_side["expected_net_pnl"] == 0.01
