from __future__ import annotations

import numpy as np
import pandas as pd

from aegis.research.short_horizon_artifact import (
    _feature_frame,
    build_quote_training_frame,
    chronological_slices,
)


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


def test_chronological_slices_are_disjoint_and_ordered():
    frame = build_quote_training_frame(
        {"EURUSD": _quotes(300)}, horizons=(5,), sample_every_s=5
    )
    slices = chronological_slices(frame)
    assert slices.train["time"].max() < slices.validation["time"].min()
    assert slices.validation["time"].max() < slices.test["time"].min()
    assert slices.test["time"].max() < slices.sealed["time"].min()
