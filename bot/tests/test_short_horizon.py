"""Focused tests for research-only short-horizon labels/features."""
from __future__ import annotations

import pandas as pd
import pytest

from aegis.research.short_horizon import (
    DEFAULT_HORIZONS_S,
    build_short_horizon_labels,
    evaluate_short_horizon_predictions,
    point_in_time_features,
)


def _quotes() -> pd.DataFrame:
    times = pd.date_range("2026-08-25T10:00:00Z", periods=7, freq="1s")
    bid = [1.1000, 1.0996, 1.0998, 1.1004, 1.1003, 1.1006, 1.1005]
    ask = [value + 0.0002 for value in bid]
    return pd.DataFrame({"time": times, "bid": bid, "ask": ask})


def test_default_horizons_are_seconds_first():
    assert DEFAULT_HORIZONS_S == (3, 5, 8, 10, 15, 20, 30, 45)


def test_labels_are_cost_aware_and_directional():
    labels = build_short_horizon_labels(_quotes(), horizons=(3, 5), cost=0.0001)
    buy = labels[(labels["side"] == "buy") & (labels["horizon_s"] == 3)].iloc[0]
    sell = labels[(labels["side"] == "sell") & (labels["horizon_s"] == 3)].iloc[0]

    assert buy["entry_price"] == pytest.approx(1.1002)
    assert buy["mfe"] == pytest.approx(0.0002)
    assert bool(buy["net_profitable_after_cost"]) is True
    assert buy["time_to_profit_s"] == pytest.approx(3.0)
    assert sell["entry_price"] == pytest.approx(1.1000)
    assert sell["mfe"] == pytest.approx(0.0002)
    assert bool(sell["net_profitable_after_cost"]) is True


def test_labels_skip_horizons_without_a_complete_future_window():
    labels = build_short_horizon_labels(_quotes(), sides=("buy",), horizons=(3, 8))
    assert set(labels["horizon_s"]) == {3}


def test_features_are_point_in_time_and_include_microstructure():
    quotes = _quotes()
    at = quotes.loc[4, "time"]
    features = point_in_time_features(quotes, at=at, symbol="EURUSD")

    assert features["symbol"] == "EURUSD"
    assert features["bid"] == pytest.approx(1.1003)
    assert features["ask"] == pytest.approx(1.1005)
    assert features["spread"] == pytest.approx(0.0002)
    assert 0.0 < features["spread_percentile"] <= 1.0
    assert "tick_velocity" in features
    assert "return_5s" in features
    assert "realized_vol_60s" in features

    changed = quotes.copy()
    changed.loc[5:, ["bid", "ask"]] += 100.0
    assert point_in_time_features(changed, at=at, symbol="EURUSD") == features


def test_features_reject_invalid_or_future_only_context():
    with pytest.raises(ValueError, match="at must be present"):
        point_in_time_features(_quotes(), at="2026-08-25T09:00:00Z")


def test_prediction_evaluation_reports_calibration_without_training():
    labels = build_short_horizon_labels(_quotes(), sides=("buy",), horizons=(3,))
    probabilities = [0.9 if value else 0.1 for value in labels["net_profitable_after_cost"]]
    report = evaluate_short_horizon_predictions(labels, probabilities)

    assert report["n"] == len(labels)
    assert 0.0 <= report["brier_score"] <= 1.0
    assert report["evaluation_scope"] == "caller_supplied_predictions"
    assert report["by_horizon"]["3"]["n"] == len(labels)
