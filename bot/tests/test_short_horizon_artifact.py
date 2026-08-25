from __future__ import annotations

import numpy as np
import pandas as pd

from aegis.research.registry import ExperimentRegistry
from aegis.research.short_horizon_artifact import (
    _feature_frame,
    _threshold_candidates,
    build_quote_training_frame,
    chronological_slices,
    record_artifact_outcome,
)


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
    columns = ["bid", "ask", "spread", "return_5s", "return_60s", "micro_volatility"]
    left = first[first["time"] < pd.Timestamp("2026-01-01T00:02:00Z")][columns].reset_index(drop=True)
    right = second[second["time"] < pd.Timestamp("2026-01-01T00:02:00Z")][columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)


def test_training_frame_has_matured_both_side_horizon_rows():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes()}, horizons=(3, 10, 45), sample_every_s=5
    )
    assert set(frame["side"]) == {"buy", "sell"}
    assert set(frame["horizon_s"]) == {3.0, 10.0, 45.0}
    assert frame["time"].max() <= pd.Timestamp("2026-01-01T00:03:15Z")
    assert {0, 1}.issuperset(set(frame["target"]))


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
    assert mfe_row["target"] == 1
    assert terminal_row["target"] == 0


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
        "threshold": 0.8,
        "horizons_s": [3, 5, 10],
        "oos": {
            "test": {"n": 100, "selected": 20, "mean_terminal_return": 0.01},
            "sealed": {"n": 100, "selected": 15, "mean_terminal_return": 0.02},
        },
    }

    experiment_id = record_artifact_outcome(metadata, registry=registry)

    row = registry.get(experiment_id)
    assert row is not None
    assert row["status"] == "accepted"
    assert row["metrics"]["test_selected"] == 20
    assert row["metrics"]["sealed_selected"] == 15
