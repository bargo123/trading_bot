"""Tests for the ML research pipeline (features, ridge, charts)."""
from __future__ import annotations

import numpy as np
import pytest

from aegis.research.ml_pipeline import (
    drawdown_svg,
    equity_curve_svg,
    feature_frame,
    ridge_fit,
    ridge_predict,
    train_and_score,
)


def _records(n: int = 60):
    rows = []
    for i in range(n):
        rows.append(
            {
                "bar_time": f"2026-08-14 {(i // 60):02d}:{(i % 60):02d}:00+00:00",
                "symbol": "EURUSD" if i % 2 == 0 else "GBPUSD",
                "side": "buy" if i % 3 else "sell",
                "regime": "range" if i % 2 else "trend",
                "structure": "none",
                "volatility": "compressing" if i % 2 else "expanding",
                "session": "asia" if i % 4 == 0 else "london",
                "h1_direction": "up" if i % 2 else "down",
                "m5_direction": "up" if i % 3 else "down",
                "outcome": 1.0 if i % 2 else -1.0,
            }
        )
    return rows


def test_feature_frame_sorts_and_encodes_hour():
    df = feature_frame(_records())
    assert df["hour_utc"].iloc[0] == 0.0
    assert df["outcome"].dtype == float


def test_ridge_fit_predict_reproduces_signal():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 3))
    y = 2.0 * x[:, 0] - 1.0 * x[:, 1] + 0.5
    w = ridge_fit(x, y, ridge=1e-6)
    pred = ridge_predict(x, w)
    assert float(((pred - y) ** 2).mean()) < 1e-8


def test_train_and_score_splits_by_time():
    df = feature_frame(_records(120))
    result = train_and_score(df, holdout_frac=0.3)
    assert result["train_n"] > result["holdout_n"]
    assert result["holdout_n"] == 36
    assert result["n_taken"] == 18
    assert len(result["equity_curve"]) == 36
    assert len(result["drawdown"]) == 36


def test_train_and_score_no_lookahead():
    df = feature_frame(_records(120))
    result = train_and_score(df, holdout_frac=0.3)
    # model-taken outcomes must be a multiset subset of the holdout outcomes
    taken_trades = [result["model_equity_curve"][0]]
    taken_trades += [
        result["model_equity_curve"][i] - result["model_equity_curve"][i - 1]
        for i in range(1, len(result["model_equity_curve"]))
    ]
    # every taken trade value must appear somewhere in the holdout equity increments
    holdout_increments = [result["equity_curve"][0]]
    holdout_increments += [
        result["equity_curve"][i] - result["equity_curve"][i - 1]
        for i in range(1, len(result["equity_curve"]))
    ]
    from collections import Counter

    taken_counter = Counter(round(float(v), 6) for v in taken_trades)
    hold_counter = Counter(round(float(v), 6) for v in holdout_increments)
    assert all(taken_counter[k] <= hold_counter[k] for k in taken_counter)


def test_equity_curve_svg_emits_svg():
    svg = equity_curve_svg([0.0, 1.0, -1.0, 2.0])
    assert svg.startswith("<svg")
    assert "path" in svg


def test_drawdown_svg_emits_svg():
    svg = drawdown_svg([0.0, -1.0, -2.0, -0.5])
    assert svg.startswith("<svg")
    assert "path" in svg


def test_equity_curve_svg_empty_is_safe():
    svg = equity_curve_svg([])
    assert svg.startswith("<svg")
    assert "no data" in svg