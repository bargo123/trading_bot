from __future__ import annotations

import numpy as np
import pandas as pd

from aegis.research.registry import ExperimentRegistry
from aegis.research.short_horizon_artifact import (
    _feature_frame,
    _execution_status,
    _metrics,
    _authorized_symbols,
    _select_decision_horizon,
    _select_threshold_for_prediction,
    _threshold_candidates,
    build_quote_training_frame,
    chronological_slices,
    record_artifact_outcome,
)
from aegis.research.short_horizon import point_in_time_features, session_features, symbol_features


def _positive_metrics(mean: float) -> dict[str, float | int]:
    return {
        "mean_terminal_return": mean,
        "expectancy_lcb95_return": mean,
        "selected": 20,
    }


def _positive_mfe_metrics(mean: float) -> dict[str, float | int]:
    return {
        "mean_harvest_return": mean,
        "harvest_lcb95_return": mean,
        "selected": 20,
    }


def _positive_captured_metrics(mean: float) -> dict[str, float | int]:
    return {
        "mean_captured_exit_return": mean,
        "captured_exit_lcb95_return": mean,
        "captured_exit_loss_count": 5,
        "selected": 20,
    }


def test_execution_candidate_requires_positive_oos_at_configured_decision_horizon():
    status, reason = _execution_status(
        target_definition="terminal_profit",
        decision_horizon_s=10,
        test_metrics=_positive_metrics(0.001),
        sealed_metrics=_positive_metrics(0.001),
        sealed_by_horizon={"10": _positive_metrics(-0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "execution_requires_captured_exit_replay"


def test_execution_candidate_requires_positive_lower_confidence_bound():
    metrics = _positive_metrics(0.001)
    metrics["expectancy_lcb95_return"] = -0.001
    status, reason = _execution_status(
        target_definition="terminal_profit",
        decision_horizon_s=10,
        test_metrics=metrics,
        sealed_metrics=_positive_metrics(0.001),
        sealed_by_horizon={"10": _positive_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "execution_requires_captured_exit_replay"


def test_execution_candidate_requires_supported_harvest_labels():
    status, reason = _execution_status(
        target_definition="unknown_target",
        decision_horizon_s=10,
        test_metrics=_positive_metrics(0.001),
        sealed_metrics=_positive_metrics(0.001),
        sealed_by_horizon={"10": _positive_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "execution_requires_supported_harvest_labels"


def test_mfe_first_is_auxiliary_only_even_with_positive_harvest_oos():
    status, reason = _execution_status(
        target_definition="mfe_first",
        decision_horizon_s=10,
        test_metrics=_positive_mfe_metrics(0.001),
        sealed_metrics=_positive_mfe_metrics(0.001),
        sealed_by_horizon={"10": _positive_mfe_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_AUXILIARY_TARGET"
    assert reason == "mfe_first_auxiliary_only"


def test_fast_harvest_is_auxiliary_only_even_with_positive_harvest_oos():
    status, reason = _execution_status(
        target_definition="fast_harvest",
        decision_horizon_s=10,
        test_metrics=_positive_mfe_metrics(0.001),
        sealed_metrics=_positive_mfe_metrics(0.001),
        sealed_by_horizon={"10": _positive_mfe_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_AUXILIARY_TARGET"
    assert reason == "fast_harvest_auxiliary_only"


def test_captured_exit_replay_is_the_only_execution_authorizing_target():
    status, reason = _execution_status(
        target_definition="captured_exit_replay",
        decision_horizon_s=10,
        test_metrics=_positive_captured_metrics(0.001),
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "EXECUTION_CANDIDATE"
    assert reason == "positive_test_sealed_decision_horizon_captured_exit_oos"


def test_mfe_first_execution_candidate_rejects_negative_harvest_lcb():
    metrics = _positive_mfe_metrics(0.001)
    metrics["harvest_lcb95_return"] = -0.001
    status, reason = _execution_status(
        target_definition="mfe_first",
        decision_horizon_s=10,
        test_metrics=metrics,
        sealed_metrics=_positive_mfe_metrics(0.001),
        sealed_by_horizon={"10": _positive_mfe_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_AUXILIARY_TARGET"
    assert reason == "mfe_first_auxiliary_only"


def test_execution_candidate_requires_positive_test_sealed_and_horizon_metrics():
    status, reason = _execution_status(
        target_definition="captured_exit_replay",
        decision_horizon_s=10,
        test_metrics=_positive_captured_metrics(0.001),
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "EXECUTION_CANDIDATE"
    assert reason == "positive_test_sealed_decision_horizon_captured_exit_oos"


def test_execution_candidate_requires_minimum_observed_captured_losses():
    sparse_losses = _positive_captured_metrics(0.001)
    sparse_losses["captured_exit_loss_count"] = 4

    status, reason = _execution_status(
        target_definition="captured_exit_replay",
        decision_horizon_s=10,
        test_metrics=sparse_losses,
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "insufficient_captured_exit_loss_evidence"


def test_decision_horizon_uses_fastest_validation_supported_horizon():
    selected, reason = _select_decision_horizon(
        {
            "10": {"mean_harvest_return": 0.001, "harvest_lcb95_return": 0.001, "selected": 5},
            "20": {"mean_harvest_return": 0.001, "harvest_lcb95_return": 0.001, "selected": 12},
            "30": {"mean_harvest_return": 0.001, "harvest_lcb95_return": 0.001, "selected": 25},
        },
        requested_horizon_s=10,
        target_definition="mfe_first",
        min_selected=20,
    )

    assert selected == 30
    assert reason == "fastest_validation_supported_horizon"


def test_symbol_authorization_requires_positive_test_and_sealed_horizon_oos():
    positive = _positive_captured_metrics(0.001)
    negative = _positive_captured_metrics(-0.001)

    authorized = _authorized_symbols(
        test_by_symbol={"EURUSD": positive, "GBPUSD": positive},
        sealed_by_symbol_horizon={
            "EURUSD": {"10": positive},
            "GBPUSD": {"10": negative},
        },
        decision_horizon_s=10,
        target_definition="captured_exit_replay",
        min_selected=10,
    )

    assert authorized == ["EURUSD"]


def test_symbol_authorization_requires_minimum_observed_captured_losses():
    positive = _positive_captured_metrics(0.001)
    sparse_losses = _positive_captured_metrics(0.001)
    sparse_losses["captured_exit_loss_count"] = 4

    authorized = _authorized_symbols(
        test_by_symbol={"EURUSD": sparse_losses, "GBPUSD": positive},
        sealed_by_symbol_horizon={
            "EURUSD": {"10": positive},
            "GBPUSD": {"10": positive},
        },
        decision_horizon_s=10,
        target_definition="captured_exit_replay",
        min_selected=10,
    )

    assert authorized == ["GBPUSD"]


def test_scope_threshold_selection_uses_validation_harvest_lcb():
    frame = pd.DataFrame(
        {
            "target": [1, 1, 0, 0],
            "terminal_return": [0.1, 0.08, -1.0, -1.0],
            "harvest_return": [0.1, 0.08, -1.0, -1.0],
            "mfe": [0.1, 0.08, 0.0, 0.0],
            "mae": [0.0, 0.0, -1.0, -1.0],
            "mid": [1.0, 1.0, 1.0, 1.0],
            "tail_loss": [0, 0, 1, 1],
            "time_to_profit_s": [1.0, 1.0, None, None],
            "time_to_failure_s": [None, None, 1.0, 1.0],
        }
    )
    prediction = {
        "probability": np.array([0.9, 0.8, 0.7, 0.2]),
        "model_probabilities": np.array([[0.9, 0.8, 0.7, 0.2], [0.9, 0.8, 0.7, 0.2]]),
        "uncertainty": np.zeros(4),
        "abstain": np.zeros(4, dtype=bool),
    }

    threshold, metrics = _select_threshold_for_prediction(
        prediction, frame, target_definition="mfe_first", min_selected=2
    )

    assert threshold == 0.8
    assert metrics["selected"] == 2
    assert metrics["harvest_lcb95_return"] > 0.0


def test_oos_metrics_include_calibration_curve_ece_and_confusion_counts():
    frame = pd.DataFrame(
        {
            "target": [0, 1, 0, 1],
            "terminal_return": [-0.1, 0.2, -0.2, 0.3],
            "tail_loss": [0, 0, 1, 0],
            "mfe": [0.1, 0.2, 0.1, 0.3],
            "mae": [-0.1, -0.1, -0.2, -0.1],
            "mid": [1.0, 1.0, 1.0, 1.0],
            "time_to_profit_s": [None, 2.0, None, 1.0],
            "time_to_failure_s": [1.0, None, 1.0, None],
        }
    )
    prediction = {
        "probability": np.array([0.1, 0.8, 0.6, 0.7]),
        "decision": np.array([False, True, False, True]),
        "abstain": np.zeros(4, dtype=bool),
    }

    metrics = _metrics(prediction, frame)

    assert 0.0 <= metrics["calibration_ece"] <= 1.0
    assert len(metrics["calibration_bins"]) > 0
    assert metrics["confusion_matrix"] == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}
    assert metrics["expectancy_lcb95_return"] <= metrics["mean_terminal_return"]
    assert "mfe_lcb95_return" in metrics
    assert "mean_mfe_return" in metrics
    assert "harvest_lcb95_return" in metrics
    assert "mean_harvest_return" in metrics
    assert "50-60%" in metrics["confidence_bands"]


def test_threshold_candidates_are_derived_from_validation_probabilities():
    probabilities = np.array([0.01, 0.02, 0.08, 0.12, 0.18, 0.27, 0.41])

    candidates = _threshold_candidates(probabilities)

    assert 0.12 in candidates
    assert max(candidates) == 0.41
    assert any(candidate < 0.5 for candidate in candidates)


def _quotes(n: int = 240) -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:00:00Z", periods=n, freq="1s")
    mid = 1.1 + np.linspace(0.0, 0.0005, n)
    return pd.DataFrame({"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001})


def test_short_horizon_features_do_not_read_future_quotes():
    original = _quotes()
    changed = original.copy()
    changed.loc[150:, ["bid", "ask"]] += 0.25
    first = _feature_frame(original, "EURUSD")
    second = _feature_frame(changed, "EURUSD")
    columns = [
        "bid", "ask", "spread", "return_5s", "return_60s", "micro_volatility",
        "spread_to_micro_vol", "spread_to_realized_vol",
    ]
    left = first[first["time"] < pd.Timestamp("2026-01-01T00:02:00Z")][columns].reset_index(drop=True)
    right = second[second["time"] < pd.Timestamp("2026-01-01T00:02:00Z")][columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


def test_training_and_runtime_share_symbol_encoding():
    quotes = _quotes()
    training = _feature_frame(quotes, "EURUSD").iloc[-1]
    runtime = point_in_time_features(quotes, at=quotes["time"].iloc[-1], symbol="EURUSD")

    for key, value in symbol_features("EURUSD").items():
        assert training[key] == value
        assert runtime[key] == value
    for key, value in session_features(0).items():
        assert training[key] == value
        assert runtime[key] == value
    for key in (
        "return_1s", "return_2s", "return_3s", "return_8s", "spread_acceleration",
        "micro_reversal", "momentum_persistence", "momentum_decay",
        "distance_to_micro_high", "distance_to_micro_low", "volatility_expansion",
        "cost_to_movement",
    ):
        assert np.isclose(float(training[key]), float(runtime[key]), equal_nan=True)


def test_training_frame_has_matured_both_side_horizon_rows():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes()}, horizons=(3, 10, 45), sample_every_s=5
    )
    assert set(frame["side"]) == {"buy", "sell"}
    assert set(frame["horizon_s"]) == {3.0, 10.0, 45.0}
    assert frame["time"].max() <= pd.Timestamp("2026-01-01T00:03:15Z")
    assert {0, 1}.issuperset(set(frame["target"]))
    assert {"time_to_profit_s", "time_to_failure_s", "harvest_return"}.issubset(frame.columns)


def test_captured_exit_replay_records_sequential_executable_outcome():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes()}, horizons=(10,), sample_every_s=1,
        target_mode="captured_exit_replay",
    )
    assert {"captured_exit_net_pnl", "captured_exit_return", "captured_exit_reason"}.issubset(frame.columns)
    assert set(frame["captured_exit_reason"]).issubset({"harvest", "abort", "timeout"})


def test_captured_exit_replay_subtracts_configured_slippage_without_double_counting_spread():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=70, freq="1s")
    mid = np.full(70, 1.10005)
    mid[0] = 1.10000
    quotes = pd.DataFrame(
        {"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001}
    )

    spread_only = build_quote_training_frame(
        {"EURUSD": quotes}, horizons=(10,), sample_every_s=1,
        target_mode="captured_exit_replay", slippage_bps=0.0,
    )
    with_slippage = build_quote_training_frame(
        {"EURUSD": quotes}, horizons=(10,), sample_every_s=1,
        target_mode="captured_exit_replay", slippage_bps=0.5,
    )
    baseline = spread_only[
        (spread_only["time"] == times[0]) & (spread_only["side"] == "buy")
    ].iloc[0]
    slipped = with_slippage[
        (with_slippage["time"] == times[0]) & (with_slippage["side"] == "buy")
    ].iloc[0]

    expected_slippage_price = 2.0 * 0.5 / 10_000.0 * 1.10000
    assert baseline["captured_exit_net_pnl"] > 0.0
    assert baseline["target"] == 1
    assert np.isclose(
        baseline["captured_exit_net_pnl"] - slipped["captured_exit_net_pnl"],
        expected_slippage_price,
    )
    assert slipped["captured_exit_net_pnl"] < 0.0
    assert slipped["target"] == 0


def test_terminal_profit_target_does_not_label_temporary_mfe_as_a_win():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=70, freq="1s")
    mid = np.full(70, 1.1)
    mid[1] = 1.1004
    mid[2:11] = np.linspace(1.1003, 1.0995, 9)
    quotes = pd.DataFrame({"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001})

    mfe = build_quote_training_frame(
        {"EURUSD": quotes}, horizons=(10,), sample_every_s=1, target_mode="mfe_first"
    )
    terminal = build_quote_training_frame(
        {"EURUSD": quotes}, horizons=(10,), sample_every_s=1, target_mode="terminal_profit"
    )
    mfe_row = mfe[(mfe["time"] == times[0]) & (mfe["side"] == "buy")].iloc[0]
    terminal_row = terminal[(terminal["time"] == times[0]) & (terminal["side"] == "buy")].iloc[0]

    assert mfe_row["mfe"] > 0
    assert mfe_row["terminal_net_pnl"] < 0
    assert mfe_row["harvest_return"] > 0
    assert mfe_row["target"] == 1
    assert terminal_row["target"] == 0


def test_fast_harvest_target_rejects_tiny_temporary_green():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=70, freq="1s")
    mid = np.full(70, 1.1)
    mid[1] = 1.10003
    mid[2:11] = np.linspace(1.10002, 1.0995, 9)
    quotes = pd.DataFrame(
        {"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001}
    )

    fast = build_quote_training_frame(
        {"EURUSD": quotes}, horizons=(10,), sample_every_s=1, target_mode="fast_harvest"
    )
    fast_row = fast[(fast["time"] == times[0]) & (fast["side"] == "buy")].iloc[0]

    assert fast_row["mfe"] > 0
    assert fast_row["harvest_return"] < 0
    assert fast_row["target"] == 0


def test_chronological_slices_are_disjoint_and_ordered():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes(300)}, horizons=(5,), sample_every_s=5
    )
    slices = chronological_slices(frame)
    assert slices.train["time"].max() < slices.validation["time"].min()
    assert slices.validation["time"].max() < slices.test["time"].min()
    assert slices.test["time"].max() < slices.sealed["time"].min()


def test_shadow_artifact_is_recorded_as_no_evidence(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    metadata = {
        "schema": "short_horizon_ensemble.v1",
        "dataset_hash": "dataset-123",
        "validation_hash": "validation-456",
        "execution_status": "SHADOW_ONLY_NO_POSITIVE_OOS",
        "threshold": 0.5,
        "horizons_s": [3, 5, 10, 30, 45],
        "oos": {
            "test": {"n": 100, "selected": 0, "positive_rate": 0.05},
            "sealed": {"n": 100, "selected": 0, "positive_rate": 0.04},
        },
    }

    experiment_id = record_artifact_outcome(metadata, registry=registry)

    row = registry.get(experiment_id)
    assert row is not None
    assert row["status"] == "failed"
    assert "positive sealed-OOS" in row["rejection_reason"]
    assert row["dataset_fingerprint"] == "dataset-123"
    assert row["metrics"]["test_selected"] == 0
    assert row["metrics"]["sealed_selected"] == 0


def test_execution_candidate_artifact_is_recorded_as_challenger(tmp_path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    metadata = {
        "schema": "short_horizon_ensemble.v1",
        "dataset_hash": "dataset-789",
        "validation_hash": "validation-000",
        "execution_status": "EXECUTION_CANDIDATE",
        "target_definition": "captured_exit_replay",
        "threshold": 0.8,
        "horizons_s": [3, 5, 10],
        "oos": {
            "test": {"n": 100, "selected": 20, "mean_captured_exit_return": 0.01},
            "sealed": {"n": 100, "selected": 15, "mean_captured_exit_return": 0.02},
        },
    }

    experiment_id = record_artifact_outcome(metadata, registry=registry)

    row = registry.get(experiment_id)
    assert row is not None
    assert row["status"] == "accepted"
    assert row["metrics"]["test_selected"] == 20
    assert row["metrics"]["sealed_selected"] == 15
