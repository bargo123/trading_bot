"""Focused tests for the optional short-horizon Firehose entry gate."""
from __future__ import annotations

from aegis.intel.firehose_brain import short_horizon_gate


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
