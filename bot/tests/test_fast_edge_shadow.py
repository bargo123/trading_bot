from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegis.research.fast_edge_shadow import (
    SHADOW_HORIZONS_S,
    build_shadow_dataset,
    chronological_shadow_slices,
    evaluate_shadow_leaderboard,
    replay_executable_path,
    shadow_model_frame,
    fit_shadow_model_space,
)


def _quotes(periods: int = 180) -> pd.DataFrame:
    times = pd.date_range("2026-01-01T00:00:00Z", periods=periods, freq="1s")
    mid = 1.1 + np.sin(np.arange(periods) / 9.0) * 0.0002
    return pd.DataFrame({"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001})


def test_shadow_horizons_cover_requested_fast_and_ceiling_windows():
    assert SHADOW_HORIZONS_S == (1, 2, 3, 5, 8, 10, 15, 20, 30, 45)


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
    assert outcome["time_to_green_s"] == 1.0
    assert outcome["time_in_red_s"] == 0.0


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
    features = shadow_model_frame(frame)
    assert "captured_exit_net_pnl" not in features.columns
    assert "future_path_observed_n" not in features.columns
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
