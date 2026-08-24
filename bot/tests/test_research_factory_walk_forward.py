"""Cost-aware, expanding walk-forward research tests."""
from __future__ import annotations

import pandas as pd

from aegis.intel.broker_math import BrokerSymbolSpec
from aegis.research.registry import ExperimentRegistry
from aegis.research_factory.core import ResearchFactory, ResearchState
from aegis.research_factory.hypothesis import Hypothesis, HypothesisOrigin
from aegis.research_factory.replay import ReplayCostEvidence
from aegis.research_factory.rules import CompileResult
from aegis.research_factory.walk_forward import walk_forward_evaluate


class _PipelineSpy:
    def __init__(self, trained_prefixes):
        self.trained_prefixes = trained_prefixes

    def train(self, train, validation=None):
        self.trained_prefixes.append(train["time"].copy())
        return [object()]

    def predict(self, validation):
        return {"spy": {"pred": [1] * len(validation)}}


def _frame():
    timestamps = pd.date_range("2026-01-01", periods=9, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "time": timestamps,
            "close": [100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "high": [100.0, 100.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0],
            "low": [99.0] * 9,
            "profit_barrier_first": [0, 1, 0, 1, 0, 1, 0, 1, 0],
        }
    )


def _compiled():
    return CompileResult(
        status="EXECUTABLE",
        reason="",
        entry_rule={"type": "breakout", "direction": "long", "window": 1},
        exit_rule={"type": "elapsed_time"},
        required_columns=frozenset({"time", "close", "high", "low"}),
        side="buy",
        max_hold_s=60,
    )


def _costs(commission_usd):
    return ReplayCostEvidence(
        BrokerSymbolSpec(1.0, 1.0, 0.01), 1.0, 0.0, commission_usd, 0.0
    )


def _hypothesis():
    return Hypothesis(
        hypothesis_id="walk-forward-hypothesis",
        origin=HypothesisOrigin.DATA_DERIVED,
        problem="test replay costs",
        proposed_mechanism="trade validated breakouts",
        features_required=["time", "high", "low", "close"],
        entry_rule={"type": "breakout", "direction": "long", "window": 1},
        exit_rule={"type": "elapsed_time"},
        side="buy",
        entry_price=None,
        invalidation_price=None,
        target_price=None,
        max_hold_s=60,
        expected_effect="positive observed net PnL",
        falsification_criterion="net PnL is not positive",
        training_period="fixture",
        validation_period="fixture",
        book_evidence=[],
        ml_evidence={"source": "fixture"},
        loss_autopsy_evidence=[],
    )


def test_walk_forward_retrains_expanding_prefixes_without_future_timestamps():
    trained_prefixes = []

    result = walk_forward_evaluate(
        _frame(),
        pipeline_factory=lambda: _PipelineSpy(trained_prefixes),
        compiled=_compiled(),
        costs=_costs(0.0),
        min_train_timestamps=2,
        validation_timestamps=2,
        step_timestamps=2,
    )

    assert result.status == "CHALLENGER"
    assert len(result.folds) == 3
    assert [len(train) for train in trained_prefixes] == [2, 4, 6]
    assert all(train.max() < fold.validation_start for train, fold in zip(trained_prefixes, result.folds))
    assert all(fold.validation_end < pd.Timestamp("2026-01-01T00:08:00Z") for fold in result.folds)
    assert result.metrics["trade_count"] > 0


def test_walk_forward_uses_observed_costs_to_reject_unprofitable_replay():
    common = {
        "pipeline_factory": lambda: _PipelineSpy([]),
        "compiled": _compiled(),
        "min_train_timestamps": 2,
        "validation_timestamps": 2,
        "step_timestamps": 2,
    }

    zero_cost = walk_forward_evaluate(_frame(), costs=_costs(0.0), **common)
    high_cost = walk_forward_evaluate(_frame(), costs=_costs(10.0), **common)

    assert zero_cost.status == "CHALLENGER"
    assert high_cost.status == "REJECTED"
    assert high_cost.metrics["net_pnl_usd"] < zero_cost.metrics["net_pnl_usd"]


def test_factory_records_no_evidence_when_walk_forward_costs_are_missing(tmp_path):
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=1, dataset_fingerprint="walk-forward-data")
    factory.experiment_registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    factory._log_event = lambda *args, **kwargs: None

    result = factory._test_hypothesis(_hypothesis(), _frame().iloc[:2], _frame().iloc[2:4], _frame().iloc[4:8])

    assert result["decision"] == "NO_EVIDENCE"
    assert result["reason"] == "walk-forward replay cost evidence is required"
    row = factory.experiment_registry.all_rows()[0]
    assert row["status"] == "failed"
    assert row["rejection_reason"] == result["reason"]


def test_factory_never_accesses_sealed_test_data(tmp_path):
    class SealedFrame:
        def __getattr__(self, name):
            raise AssertionError(f"sealed data was accessed: {name}")

    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=2, dataset_fingerprint="nonsealed")
    factory.experiment_registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    factory._log_event = lambda *args, **kwargs: None

    result = factory._test_hypothesis(
        _hypothesis(), _frame().iloc[:2], _frame().iloc[2:4], SealedFrame()
    )

    assert result["decision"] == "NO_EVIDENCE"


def test_walk_forward_rejects_overlapping_validation_windows():
    result = walk_forward_evaluate(
        _frame(), pipeline_factory=lambda: _PipelineSpy([]), compiled=_compiled(),
        costs=_costs(0), min_train_timestamps=2, validation_timestamps=3,
        step_timestamps=2,
    )
    assert result.status == "NOT_EXECUTABLE"


def test_walk_forward_purges_label_horizon_from_training_prefix():
    trained = []
    result = walk_forward_evaluate(
        _frame(), pipeline_factory=lambda: _PipelineSpy(trained), compiled=_compiled(),
        costs=_costs(0), min_train_timestamps=3, validation_timestamps=2,
        step_timestamps=2, label_horizon=1,
    )
    assert result.folds[0].train_end < result.folds[0].validation_start
    assert trained[0].max() == _frame().iloc[1]["time"]


def test_aggregate_drawdown_uses_ordered_trades_across_folds(monkeypatch):
    from aegis.research_factory.replay import ReplayResult, ReplayTrade
    import aegis.research_factory.walk_forward as walk_forward

    trades = iter(
        [
            (10.0, 0.0),
            (-15.0, 0.0),
            (10.0, 0.0),
        ]
    )

    def replay(*args, **kwargs):
        pnl, per_fold_drawdown = next(trades)
        trade = ReplayTrade("buy", 0, 1, 1, 1, "fixture", pnl, 0, pnl)
        return ReplayResult("COMPLETED", (trade,), {
            "trade_count": 1.0, "gross_pnl_usd": pnl, "cost_usd": 0.0,
            "net_pnl_usd": pnl, "expectancy_usd": pnl,
            "max_drawdown_usd": per_fold_drawdown,
        }, "")

    monkeypatch.setattr(walk_forward, "replay_hypothesis", replay)
    result = walk_forward_evaluate(
        _frame(), pipeline_factory=lambda: _PipelineSpy([]), compiled=_compiled(),
        costs=_costs(0), min_train_timestamps=2, validation_timestamps=2,
        step_timestamps=2,
    )
    assert result.metrics["max_drawdown_usd"] == 15.0


def test_factory_persists_compiler_exception_as_failed_without_metrics(monkeypatch, tmp_path):
    import aegis.research_factory.core as core

    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=3, dataset_fingerprint="nonsealed")
    factory.experiment_registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    factory._log_event = lambda *args, **kwargs: None
    monkeypatch.setattr(core, "compile_hypothesis", lambda *args: (_ for _ in ()).throw(RuntimeError("compiler exploded")))

    result = factory._test_hypothesis(_hypothesis(), _frame().iloc[:2], _frame().iloc[2:4], object())

    assert result["decision"] == "FAILED"
    assert result["reason"] == "walk-forward evaluation failed: compiler exploded"
    row = factory.experiment_registry.all_rows()[0]
    assert row["status"] == "failed"
    assert row["metrics"] == {}


def test_walk_forward_retains_failed_fold_without_fabricated_metrics():
    class BrokenPipeline:
        def train(self, train):
            raise RuntimeError("pipeline exploded")

    result = walk_forward_evaluate(
        _frame(), pipeline_factory=BrokenPipeline, compiled=_compiled(), costs=_costs(0),
        min_train_timestamps=2, validation_timestamps=2, step_timestamps=2,
    )

    assert result.status == "FAILED"
    assert result.reason == "walk-forward fold failed: pipeline exploded"
    assert result.metrics is None
    assert result.folds[0].status == "FAILED"
    assert result.folds[0].trade_count is None
    assert result.folds[0].net_pnls_usd == ()
