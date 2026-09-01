from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegis.research.registry import ExperimentRegistry
from aegis.research.short_horizon_artifact import (
    _feature_frame,
    _execution_status,
    _model_frame,
    _metrics,
    _authorized_symbols,
    _select_decision_horizon,
    _select_threshold_for_prediction,
    _threshold_candidates,
    build_quote_training_frame,
    captured_win_calibration_metrics,
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
        "captured_exit_win_count": 995,
        "captured_exit_win_rate": 0.995,
        "captured_exit_win_lcb95": 0.985,
        "selected": 1000,
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
        validation_metrics=_positive_captured_metrics(0.001),
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
        validation_metrics=_positive_captured_metrics(0.001),
        test_metrics=_positive_captured_metrics(0.001),
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "EXECUTION_CANDIDATE"
    assert reason == "positive_test_sealed_decision_horizon_captured_exit_oos"


def test_execution_candidate_requires_positive_validation_oos():
    status, reason = _execution_status(
        target_definition="captured_exit_replay",
        decision_horizon_s=10,
        validation_metrics=_positive_captured_metrics(-0.001),
        test_metrics=_positive_captured_metrics(0.001),
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "validation_captured_exit_oos_not_positive"


def test_execution_candidate_requires_minimum_observed_captured_losses():
    sparse_losses = _positive_captured_metrics(0.001)
    sparse_losses["captured_exit_loss_count"] = 4

    status, reason = _execution_status(
        target_definition="captured_exit_replay",
        decision_horizon_s=10,
        validation_metrics=_positive_captured_metrics(0.001),
        test_metrics=sparse_losses,
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "insufficient_captured_exit_loss_evidence"


def test_execution_candidate_requires_captured_win_rate_target():
    weak = _positive_captured_metrics(0.001)
    weak["captured_exit_win_lcb95"] = 0.94
    status, reason = _execution_status(
        target_definition="captured_exit_replay",
        decision_horizon_s=10,
        validation_metrics=_positive_captured_metrics(0.001),
        test_metrics=weak,
        sealed_metrics=_positive_captured_metrics(0.001),
        sealed_by_horizon={"10": _positive_captured_metrics(0.001)},
    )

    assert status == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert reason == "captured_exit_win_rate_lcb95_below_target"


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


def test_captured_threshold_selection_requires_loss_coverage():
    probabilities = np.array(
        [0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.93, 0.92, 0.91, 0.90, 0.89, 0.88]
    )
    captured = [0.1] * 7 + [-0.01] * 5
    frame = pd.DataFrame(
        {
            "target": [int(value > 0) for value in captured],
            "terminal_return": captured,
            "captured_exit_return": captured,
            "captured_exit_net_pnl": captured,
            "mfe": captured,
            "mae": [0.0] * len(captured),
            "mid": [1.0] * len(captured),
            "tail_loss": [0] * len(captured),
            "time_to_profit_s": [1.0] * len(captured),
            "time_to_failure_s": [None] * 7 + [1.0] * 5,
        }
    )
    prediction = {
        "probability": probabilities,
        "model_probabilities": np.vstack([probabilities, probabilities]),
        "uncertainty": np.zeros(len(probabilities)),
        "abstain": np.zeros(len(probabilities), dtype=bool),
    }

    threshold, metrics = _select_threshold_for_prediction(
        prediction, frame, target_definition="captured_exit_replay", min_selected=2
    )

    assert threshold == pytest.approx(0.88)
    assert metrics["captured_exit_loss_count"] >= 5


def test_model_frame_excludes_future_green_time_alias():
    frame = pd.DataFrame(
        {
            "target": [0, 1],
            "terminal_return": [-0.01, 0.01],
            "time_to_first_net_green_s": [1.0, 2.0],
            "time_to_first_net_green": [1.0, 2.0],
            "entry_spread_price": [0.0001, 0.0001],
            "mid": [1.0, 1.0],
        }
    )

    model_frame = _model_frame(frame)

    assert "time_to_first_net_green_s" not in model_frame.columns
    assert "time_to_first_net_green" not in model_frame.columns
    assert "entry_spread_price" in model_frame.columns


def test_model_frame_excludes_all_future_outcome_aliases():
    frame = pd.DataFrame(
        {
            "target": [0],
            "mid": [1.0],
            "return_5s": [0.001],
            "pnl_5s": [0.2],
            "green_within_5s": [True],
            "captured_win_5s": [True],
            "exit_capturedexit_net_pnl": [0.2],
            "future_path_observed_n": [4],
            "first_green": [True],
            "immediate_adverse_move": [-0.1],
            "time_to_mfe_s": [1.0],
            "winner_giveback": [0.2],
        }
    )

    model_frame = _model_frame(frame)

    assert "return_5s" in model_frame.columns
    assert not any(
        str(column).startswith(
            ("pnl_", "green_", "captured_", "exit_", "future_", "time_to_")
        )
        for column in model_frame.columns
    )
    assert "first_green" not in model_frame.columns
    assert "immediate_adverse_move" not in model_frame.columns
    assert "winner_giveback" not in model_frame.columns


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


def test_feature_frame_keeps_actual_last_tick_time_within_each_second():
    quotes = pd.DataFrame(
        {
            "time": pd.to_datetime(
                [
                    "2026-01-01T00:00:00.100Z",
                    "2026-01-01T00:00:00.900Z",
                    "2026-01-01T00:00:01.100Z",
                    "2026-01-01T00:00:02.100Z",
                ],
                utc=True,
            ),
            "bid": [1.0, 1.1, 1.2, 1.3],
            "ask": [1.01, 1.11, 1.21, 1.31],
        }
    )

    features = _feature_frame(quotes, "EURUSD", minimum_history_rows=2)

    first = features.iloc[0]
    assert first["time"] == pd.Timestamp("2026-01-01T00:00:00.900Z")
    assert first["bid"] == pytest.approx(1.1)


def test_captured_replay_thresholds_do_not_read_future_spreads():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=70, freq="1s")
    bid = np.full(70, 1.0)
    bid[1] = 1.0004
    bid[2:11] = 0.9997
    ask = bid + 0.0001
    original = pd.DataFrame({"time": times, "bid": bid, "ask": ask})

    changed = original.copy()
    changed.loc[20:, "ask"] = changed.loc[20:, "bid"] + 0.01

    original_frame = build_quote_training_frame(
        {"EURUSD": original}, horizons=(10,), sample_every_s=1,
        target_mode="captured_exit_replay",
    )
    changed_frame = build_quote_training_frame(
        {"EURUSD": changed}, horizons=(10,), sample_every_s=1,
        target_mode="captured_exit_replay",
    )
    original_row = original_frame[
        (original_frame["time"] == times[0]) & (original_frame["side"] == "buy")
    ].iloc[0]
    changed_row = changed_frame[
        (changed_frame["time"] == times[0]) & (changed_frame["side"] == "buy")
    ].iloc[0]

    assert original_row["captured_exit_reason"] == "harvest"
    assert original_row["captured_win_label"] == 1
    assert changed_row["captured_exit_reason"] == "harvest"
    assert changed_row["captured_win_label"] == 1


def test_training_frame_skips_entries_without_a_full_horizon_quote():
    times = list(pd.date_range("2026-01-01T00:00:00Z", periods=30, freq="1s"))
    times.extend(pd.date_range("2026-01-01T00:00:40Z", periods=40, freq="1s"))
    mid = np.full(len(times), 1.1)
    quotes = pd.DataFrame({
        "time": times,
        "bid": mid - 0.00001,
        "ask": mid + 0.00001,
    })

    frame = build_quote_training_frame(
        {"EURUSD": quotes}, horizons=(10,), sample_every_s=1,
        target_mode="captured_exit_replay",
    )

    assert pd.Timestamp("2026-01-01T00:00:25Z") not in set(frame["time"])


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


def test_captured_exit_returns_are_invariant_to_broker_usd_conversion_scale():
    quotes = _quotes()
    raw = build_quote_training_frame(
        {"EURUSD": quotes},
        horizons=(10,),
        sample_every_s=5,
        target_mode="captured_exit_replay",
        usd_per_price_unit_by_symbol={"EURUSD": 1.0},
    )
    broker_usd = build_quote_training_frame(
        {"EURUSD": quotes},
        horizons=(10,),
        sample_every_s=5,
        target_mode="captured_exit_replay",
        usd_per_price_unit_by_symbol={"EURUSD": 1000.0},
    )

    raw_row = raw.iloc[0]
    broker_row = broker_usd.iloc[0]
    assert broker_row["captured_exit_net_pnl"] == pytest.approx(
        raw_row["captured_exit_net_pnl"] * 1000.0
    )
    assert broker_row["captured_exit_return"] == pytest.approx(
        raw_row["captured_exit_return"]
    )
    assert broker_row["terminal_return"] == pytest.approx(raw_row["terminal_return"])
    assert broker_row["harvest_return"] == pytest.approx(raw_row["harvest_return"])
    assert broker_row["mfe_return"] == pytest.approx(raw_row["mfe_return"])
    assert broker_row["mae_return"] == pytest.approx(raw_row["mae_return"])


def test_captured_labels_keep_exact_identity_and_provenance():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes()},
        horizons=(3, 10),
        sample_every_s=5,
        target_mode="captured_exit_replay",
        mechanism="micro_momentum_continuation",
        provenance="synthetic_fixture",
    )

    required = {
        "symbol", "side", "mechanism", "horizon_s", "label_provenance",
        "captured_win_label", "net_pnl", "mfe", "mae",
        "time_to_first_net_green_s", "never_green", "green_then_loser",
        "time_to_peak_s", "spread_price", "commission_usd", "slippage_price",
    }
    assert required.issubset(frame.columns)
    assert set(frame["mechanism"]) == {"micro_momentum_continuation"}
    assert set(frame["label_provenance"]) == {"synthetic_fixture"}
    assert set(frame["captured_win_label"]).issubset({0, 1})
    assert (frame["captured_win_label"] == (frame["net_pnl"] > 0)).all()


def test_captured_win_probability_is_calibrated_against_net_winner_not_mfe():
    report = captured_win_calibration_metrics(
        [1.0, 0.0, 1.0, 0.0],
        [0.25, -0.01, 0.10, -0.02],
    )

    assert report["target"] == "captured_exit_net_pnl > 0"
    assert report["n"] == 4
    assert report["captured_win_count"] == 2
    assert report["brier_score"] == pytest.approx(0.0)
    assert report["calibration_ece"] == pytest.approx(0.0)


def test_horizon_specific_capture_labels_can_differ():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=25, freq="1s")
    mid = np.full(25, 1.10000)
    mid[1] = 1.10003
    mid[2] = 1.10001
    mid[3] = 1.10002
    mid[4] = 1.10010
    quotes = pd.DataFrame(
        {"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001}
    )

    frame = build_quote_training_frame(
        {"EURUSD": quotes},
        horizons=(3, 10),
        sample_every_s=1,
        target_mode="captured_exit_replay",
    )
    first_entry = frame[frame["time"] == times[0]]
    by_horizon = {
        int(row.horizon_s): int(row.captured_win_label)
        for row in first_entry[first_entry["side"] == "buy"].itertuples()
    }

    assert by_horizon[3] == 0
    assert by_horizon[10] == 1


def test_captured_labels_use_executable_entry_and_liquidation_sides():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=12, freq="1s")
    buy_mid = np.full(12, 1.10000)
    buy_mid[1:] = 1.10010
    sell_mid = np.full(12, 1.10000)
    sell_mid[1:] = 1.09990
    buy_frame = build_quote_training_frame(
        {"EURUSD": pd.DataFrame({
            "time": times, "bid": buy_mid - 0.00001, "ask": buy_mid + 0.00001,
        })},
        horizons=(3,), sample_every_s=1, target_mode="captured_exit_replay",
    )
    sell_frame = build_quote_training_frame(
        {"EURUSD": pd.DataFrame({
            "time": times, "bid": sell_mid - 0.00001, "ask": sell_mid + 0.00001,
        })},
        horizons=(3,), sample_every_s=1, target_mode="captured_exit_replay",
    )
    buy = buy_frame[(buy_frame["time"] == times[0]) & (buy_frame["side"] == "buy")].iloc[0]
    sell = sell_frame[(sell_frame["time"] == times[0]) & (sell_frame["side"] == "sell")].iloc[0]

    assert buy["entry_price"] == pytest.approx(1.10001)
    assert buy["net_pnl"] == pytest.approx(0.00008)
    assert sell["entry_price"] == pytest.approx(1.09999)
    assert sell["net_pnl"] == pytest.approx(0.00008)


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


def test_chronological_slices_purge_label_horizon_between_splits():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes(600)}, horizons=(20,), sample_every_s=1
    )
    slices = chronological_slices(frame)
    purge = pd.Timedelta(seconds=20)

    assert slices.train["time"].max() + purge < slices.validation["time"].min()
    assert slices.validation["time"].max() + purge < slices.test["time"].min()
    assert slices.test["time"].max() + purge < slices.sealed["time"].min()


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
