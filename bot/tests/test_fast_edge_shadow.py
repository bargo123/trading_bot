from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegis.research.fast_edge_shadow import (
    SHADOW_HORIZONS_S,
    _calibrate_probability_vector,
    build_shadow_dataset,
    chronological_shadow_slices,
    evaluate_shadow_leaderboard,
    fast_winner_feature_discovery,
    replay_executable_path,
    shadow_model_frame,
    fit_shadow_model_space,
    evaluate_exit_policies,
    fit_multi_outcome_models,
    fit_segmented_logistic_models,
)


def _quotes(periods: int = 180) -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:00:00Z", periods=periods, freq="1s")
    mid = 1.1 + np.sin(np.arange(periods) / 9.0) * 0.0002
    return pd.DataFrame({"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001})


def test_shadow_horizons_cover_requested_fast_and_ceiling_windows():
    assert SHADOW_HORIZONS_S == (1, 2, 3, 5, 8, 10, 15, 20, 30, 45)


def test_segment_rates_use_full_oos_observation_window_not_sparse_group_span():
    times = list(pd.date_range("2026-01-01T00:00:00Z", periods=21, freq="1s"))
    times.append(pd.Timestamp("2026-01-01T01:00:00Z"))
    frame = pd.DataFrame(
        {
            "time": times,
            "symbol": ["EURUSD"] * 21 + ["GBPUSD"],
            "side": ["buy"] * 22,
            "session": ["london"] * 22,
            "regime": ["normal_volatility"] * 22,
            "structure": ["m1_range_or_pullback"] * 22,
            "family": ["universal_quote_entry"] * 22,
            "horizon_s": [5.0] * 22,
            "captured_exit_return": [0.001] * 22,
            "target": [1] * 22,
            "time_to_green_s": [1.0] * 22,
        }
    )
    rows = evaluate_shadow_leaderboard(
        frame,
        {"test_model": np.ones(len(frame))},
        thresholds=(0.5,),
        min_samples=20,
    )
    assert len(rows) == 1
    assert rows[0]["selected"] == 21
    assert rows[0]["observation_window_hours"] == pytest.approx(1.0)
    assert rows[0]["candidate_arrivals_per_hour"] == pytest.approx(21.0)
    assert rows[0]["non_overlapping_selected"] == 5
    assert rows[0]["trades_per_hour"] == pytest.approx(5.0)


def test_replay_uses_executable_sides_and_stops_sequentially():
    outcome = replay_executable_path(
        entry_time=pd.Timestamp("2026-01-01T00:00:00Z"),
        entry_bid=1.09999,
        entry_ask=1.10001,
        future_times=pd.date_range("2026-01-01T00:00:01Z", periods=3, freq="1s"),
        future_bid=np.array([1.10002, 1.10010, 1.10020]),
        future_ask=np.array([1.10004, 1.10012, 1.10022]),
        side="buy",
        horizon_s=3,
    )
    assert outcome["captured_exit_reason"] == "harvest"
    assert outcome["captured_exit_net_pnl"] == pytest.approx(0.00009)
    assert outcome["first_green"] is True
    assert outcome["first_profitable_executable_close"] is True
    assert outcome["time_to_green_s"] == 1.0
    assert outcome["time_in_red_s"] == 0.0


def test_causal_exit_policy_variants_do_not_use_future_max_as_entry_authority():
    kwargs = {
        "entry_time": pd.Timestamp("2026-01-01T00:00:00Z"),
        "entry_bid": 1.09999,
        "entry_ask": 1.10001,
        "future_times": pd.date_range("2026-01-01T00:00:01Z", periods=5, freq="1s"),
        "future_bid": np.array([1.10002, 1.10010, 1.10020, 1.10012, 1.10008]),
        "future_ask": np.array([1.10004, 1.10012, 1.10022, 1.10014, 1.10010]),
        "side": "buy",
        "horizon_s": 5,
    }
    meaningful = replay_executable_path(**kwargs, exit_policy="first_meaningful_green")
    protected = replay_executable_path(**kwargs, exit_policy="mfe_protection")
    no_progress_kwargs = dict(kwargs)
    no_progress_kwargs["future_bid"] = np.array([1.09999, 1.09999, 1.09999, 1.09999, 1.09999])
    no_progress_kwargs["future_ask"] = np.array([1.10001, 1.10001, 1.10001, 1.10001, 1.10001])
    no_progress = replay_executable_path(**no_progress_kwargs, exit_policy="no_progress_3s")
    assert meaningful["exit_policy"] == "first_meaningful_green"
    assert meaningful["captured_exit_reason"] == "harvest"
    assert protected["captured_exit_reason"] == "giveback"
    assert protected["captured_exit_net_pnl"] < protected["mfe"]
    assert no_progress["captured_exit_reason"] == "no_progress"


def test_shadow_dataset_is_universal_and_outcome_columns_are_not_features():
    frame = build_shadow_dataset(
        {"EURUSD": _quotes(), "USDJPY": _quotes().copy()},
        horizons=(1, 2, 5),
        sample_every_s=2,
    )
    assert set(frame["symbol"]) == {"EURUSD", "USDJPY"}
    assert set(frame["horizon_s"]) == {1.0, 2.0, 5.0}
    assert set(frame["side"]) == {"buy", "sell"}
    assert set(frame["candidate_authority"]) == {"SHADOW_ONLY"}
    assert set(frame["family_version"]) == {"quote_microstructure_v1"}
    assert {"m1_return", "m5_return", "m15_return", "m1_range", "structure_context", "regime_context"}.issubset(
        frame.columns
    )
    assert {"pnl_1s", "pnl_2s", "pnl_5s", "green_within_1s", "captured_win_5s"}.issubset(frame.columns)
    assert {
        "exit_capturedexitreplay_return", "exit_mfeprotection_return",
        "exit_noprogress3s_time_s",
    }.issubset(frame.columns)
    features = shadow_model_frame(frame)
    assert "captured_exit_net_pnl" not in features.columns
    assert "future_path_observed_n" not in features.columns
    assert "pnl_1s" not in features.columns
    assert "green_within_5s" not in features.columns
    assert "structure_context" not in features.columns
    assert {"return_1s", "return_2s", "return_3s", "micro_reversal", "volatility_expansion"}.issubset(
        features.columns
    )
    assert "target" in features.columns


def test_shadow_slices_are_strictly_chronological():
    frame = build_shadow_dataset({"EURUSD": _quotes(260)}, horizons=(1, 5), sample_every_s=2)
    slices = chronological_shadow_slices(frame)
    assert slices.train["time"].max() < slices.validation["time"].min()
    assert slices.validation["time"].max() < slices.test["time"].min()
    assert slices.test["time"].max() < slices.sealed["time"].min()


def test_leaderboard_reports_captured_metrics_and_is_ranked():
    frame = build_shadow_dataset({"EURUSD": _quotes(260)}, horizons=(1, 5), sample_every_s=2)
    probabilities = np.where(frame["target"].to_numpy() == 1, 0.9, 0.1)
    rows = evaluate_shadow_leaderboard(
        frame,
        {"test_model": probabilities},
        thresholds=(0.5, 0.8),
        min_samples=2,
    )
    assert rows
    assert rows[0]["captured_exit_expectancy"] >= rows[-1]["captured_exit_expectancy"]
    assert {
        "symbol", "side", "session", "regime", "structure", "family", "horizon_s",
        "model", "threshold", "captured_exit_expectancy", "captured_exit_pf",
        "p95_loss", "p99_loss", "calibration_ece",
    }.issubset(rows[0])


def test_shadow_model_space_searches_local_models_without_authority():
    frame = build_shadow_dataset({"EURUSD": _quotes(320)}, horizons=(1, 5), sample_every_s=2)
    report = fit_shadow_model_space(frame, min_samples=2)
    assert {"logistic", "regularized_logistic", "hist_gradient_boosting", "gradient_boosting", "random_forest"}.issubset(
        set(report["model_names"]) | set(report["model_errors"])
    )
    assert report["oos"]["sealed_n"] > 0
    assert all(row["model"] in report["model_names"] for row in report["leaderboard"])
    assert set(report["calibration_methods"]) == set(report["model_names"])
    assert {"model_probability_mean", "model_disagreement", "prediction_vector"}.issubset(
        report["sealed_predictions"].columns
    )


def test_probability_calibration_uses_only_prior_calibration_observations():
    raw = np.array([0.05, 0.20, 0.80, 0.95])
    actual = np.array([0, 0, 1, 1])
    calibrated, method = _calibrate_probability_vector(raw, actual, np.array([0.10, 0.90]))
    assert method == "isotonic_validation"
    assert np.all((calibrated >= 0.0) & (calibrated <= 1.0))
    assert calibrated[0] < calibrated[1]


def test_fast_winner_feature_discovery_compares_oos_groups_without_outcome_features():
    frame = build_shadow_dataset({"EURUSD": _quotes(320)}, horizons=(1, 5), sample_every_s=2)
    report = fast_winner_feature_discovery(
        chronological_shadow_slices(frame).sealed,
        horizons=(1, 5),
        top_n=5,
    )
    assert report["analysis_scope"] == "descriptive_sealed_oos"
    assert {"fast_clean_winner", "slow_or_losing", "tail_loss"}.issubset(report["groups"])
    assert "1" in report["horizons"]
    assert report["horizons"]["1"]["fast_clean_n"] >= 0
    assert all(
        "captured_exit" not in row["feature"] and "green_within" not in row["feature"]
        for row in report["horizons"]["1"]["top_feature_differences"]
    )


def test_exit_policy_comparison_is_segmented_and_cost_aware():
    frame = build_shadow_dataset({"EURUSD": _quotes(260)}, horizons=(1, 5), sample_every_s=2)
    rows = evaluate_exit_policies(frame, min_samples=2)
    assert rows
    assert {"captured_exit_replay", "mfe_protection", "no_progress_3s"}.issubset(
        {row["exit_policy"] for row in rows}
    )
    assert {"win_rate", "captured_exit_pf", "avg_loss", "p95_loss", "median_exit_time_s"}.issubset(rows[0])


def test_multi_outcome_models_report_sealed_probabilities_and_expectations():
    frame = build_shadow_dataset({"EURUSD": _quotes(260)}, horizons=(1, 2, 3, 5, 10, 20), sample_every_s=2)
    report = fit_multi_outcome_models(frame)
    assert {"P_GREEN_1S", "P_GREEN_10S", "P_TAIL_LOSS", "P_WINNER_GIVEBACK"}.issubset(
        report["probability"]
    )
    assert {"EXPECTED_NET_PNL", "EXPECTED_MFE", "EXPECTED_TIME_TO_GREEN"}.issubset(
        report["regression"]
    )
    assert all(value["status"] in {"SEALED_OOS", "missing_target", "single_class_train"} for value in report["probability"].values())


def test_segmented_models_are_chronological_and_dimension_scoped():
    frame = build_shadow_dataset(
        {"EURUSD": _quotes(320), "GBPUSD": _quotes(320)}, horizons=(1, 5), sample_every_s=2
    )
    report = fit_segmented_logistic_models(
        frame, min_train_samples=20, min_validation_samples=5, min_sealed_samples=5
    )
    assert {"symbol", "side", "session", "horizon_s"}.issubset(report["dimensions"])
    assert report["accepted_model_count"] > 0
    assert all("segment_dimension" in row and "captured_exit_pf" in row for row in report["oos_leaderboard"])
