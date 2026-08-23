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
