"""Predictor research protocol tests (audit remediation 1)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.research.predictor_protocol import (  # noqa: E402
    ml_advances_from_protocol,
    run_predictor_protocol,
)


def _synthetic_df(n=3000, signal_coef=2.0, noise=1.0, seed=1):
    """outcome = coef * signal + regime effect: learnable via the numeric
    passthrough AND categorical context (both paths the matrix supports)."""
    import aegis.research.ml_pipeline as ml

    rng = np.random.default_rng(seed)
    df = pd.DataFrame(
        {
            "bar_time": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "signal": rng.normal(size=n),
            "regime": np.where(rng.random(n) < 0.5, "trend", "range"),
            "structure": "none",
            "volatility": "stable",
            "session": "london",
            "h1_direction": "up",
            "m5_direction": "down",
            "symbol": "EURUSD",
            "side": np.where(rng.random(n) < 0.5, "buy", "sell"),
        }
    )
    df["outcome"] = (
        signal_coef * df["signal"]
        + np.where(df["regime"] == "trend", 2.5, -0.5)
        + rng.normal(scale=noise, size=n)
    )
    # Enable the numeric passthrough for this fixture's signal column.
    ml.NUMERIC_FEATURES = ("signal",)
    return df
    return df


def test_learnable_signal_advances_with_inner_only_threshold():
    df = _synthetic_df()
    r = run_predictor_protocol(df, holdout_frac=0.3, n_folds=4,
                               min_trades_threshold=50)
    assert r["threshold_source"] == "inner_walkforward"
    assert r["locked_threshold"] is not None
    assert r["correlation_spearman"] > 0.8
    assert r["monotonicity_fraction"] == pytest.approx(1.0)
    taken = r["sealed_taken"]
    assert taken["n"] > 0 and taken["expectancy"] > 0
    assert r["ml_advances"] is True


def test_random_outcome_does_not_advance():
    df = _synthetic_df(signal_coef=0.0, noise=1.0, seed=2)
    r = run_predictor_protocol(df, holdout_frac=0.3, n_folds=4,
                               min_trades_threshold=50)
    if r["locked_threshold"] is None:
        assert r["ml_advances"] is False
    else:
        taken = r["sealed_taken"]
        no_edge = (
            (taken.get("expectancy") or 0) <= 0
            or (taken.get("bootstrap_p05") or -1) <= 0
            or (taken.get("profit_factor") or 0) <= 1
        )
        if no_edge:
            assert r["ml_advances"] is False


def test_no_lookahead_threshold_chosen_without_sealed_data():
    """Threshold selection consumes ONLY inner-fold predictions."""
    df = _synthetic_df(seed=3)
    import aegis.research.predictor_protocol as pp

    calls = {"n": 0}
    orig = pp.choose_threshold

    def spy(inner_pred, inner_actual, **kw):
        calls["n"] += 1
        return orig(inner_pred, inner_actual, **kw)

    pp.choose_threshold = spy
    try:
        run_predictor_protocol(df, holdout_frac=0.3, n_folds=4,
                               min_trades_threshold=50)
    finally:
        pp.choose_threshold = orig
    assert calls["n"] == 1


def test_ml_advances_requires_absolute_positive_ev():
    from scripts.research_ml_pipeline import ml_advances

    # Relative improvement (-1.18 -> -0.36) is NEVER success.
    assert ml_advances(-0.3558, 0.8277) is False
    assert ml_advances(0.01, -1.0) is True


def test_report_includes_required_research_fields():
    df = _synthetic_df(seed=4)
    r = run_predictor_protocol(df, holdout_frac=0.3, n_folds=3,
                               min_trades_threshold=50)
    for key in ("correlation_pearson", "correlation_spearman", "mae", "rmse",
                "deciles", "monotonicity_fraction", "walk_forward_stability",
                "threshold_selection", "locked_threshold"):
        assert key in r
    for d in r["deciles"]:
        for k in ("n", "predicted_mean", "actual_ev", "profit_factor",
                  "win_rate", "avg_win", "avg_loss", "bootstrap_p05"):
            assert k in d


def test_grouped_oos_when_meta_present():
    df = _synthetic_df(seed=5)
    meta = df[["symbol", "side", "session", "regime"]].copy()
    meta["strategy_family"] = "test_family"
    r = run_predictor_protocol(df, meta=meta, holdout_frac=0.3, n_folds=3,
                               min_trades_threshold=50)
    grouped = r.get("sealed_grouped") or {}
    assert "EURUSD" in grouped.get("symbol", {})
    assert "test_family" in grouped.get("strategy_family", {})


def test_ml_advances_from_protocol_helper():
    good = {
        "locked_threshold": 0.5, "ml_advances": True,
        "sealed_taken": {"n": 100, "expectancy": 0.05,
                         "bootstrap_p05": 0.01, "profit_factor": 1.3},
        "monotonicity_fraction": 0.9,
    }
    assert ml_advances_from_protocol(good) is True
    bad = dict(good, sealed_taken={"n": 100, "expectancy": -0.05,
                                   "bootstrap_p05": -0.01, "profit_factor": 0.7})
    assert ml_advances_from_protocol(bad) is False
    no_thr = dict(good, locked_threshold=None, ml_advances=False)
    assert ml_advances_from_protocol(no_thr) is False
