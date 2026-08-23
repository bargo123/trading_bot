from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.research.fingerprint import config_fingerprint
from aegis.research.registry import (
    DuplicateExperimentError,
    EquivalentExperimentError,
    ExperimentRegistry,
)
from aegis.research.sealed import (
    SealedHoldoutError,
    SealedHoldoutStore,
    freeze_candidate,
)
from aegis.research_factory.evaluation import (
    evaluate_candidate_once,
    record_outcome,
)
from aegis.research_factory.core import ResearchFactory, ResearchState
from aegis.research_factory.hypothesis import Hypothesis, HypothesisOrigin


def _hypothesis(hypothesis_id: str = "hyp_eval") -> Hypothesis:
    return Hypothesis(
        hypothesis_id=hypothesis_id,
        origin=HypothesisOrigin.DATA_DERIVED,
        problem="breakouts may continue after the prior two-bar high",
        proposed_mechanism="buy a two-bar breakout and exit after elapsed time",
        features_required=["time", "high", "low", "close"],
        entry_rule={"type": "breakout", "direction": "long", "window": 2},
        exit_rule={"type": "elapsed_time", "max_hold_s": 120},
        side="buy",
        entry_price=None,
        invalidation_price=None,
        target_price=None,
        max_hold_s=120,
        expected_effect="positive net expectancy after observed costs",
        falsification_criterion="net expectancy is not positive",
        training_period="2026-01-01 to 2026-01-31",
        validation_period="2026-02-01 to 2026-02-07",
        book_evidence=[],
        ml_evidence={"source": "walk-forward fixture"},
        loss_autopsy_evidence=[],
        created_at="2026-08-23T00:00:00+00:00",
    )


_PARAMS = {
    "features_required": ["time", "high", "low", "close"],
    "entry_rule": {"type": "breakout", "direction": "long", "window": 2},
    "exit_rule": {"type": "elapsed_time", "max_hold_s": 120},
    "side": "buy",
    "entry_price": None,
    "invalidation_price": None,
    "target_price": None,
    "max_hold_s": 120,
}


@pytest.mark.parametrize(
    ("factory_status", "metrics"),
    [
        ("NO_DATA", None),
        ("NO_EVIDENCE", None),
        ("NOT_EXECUTABLE", None),
        ("FAILED", None),
        ("REJECTED", {"expectancy": -0.25, "n_trades": 4}),
        ("CHALLENGER", {"expectancy": 0.4, "n_trades": 24}),
    ],
)
def test_record_outcome_persists_every_terminal_status_without_fabricated_metrics(
    tmp_path: Path,
    factory_status: str,
    metrics: dict | None,
):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    hypothesis = _hypothesis()
    reason = f"observed terminal outcome: {factory_status}"

    experiment_id = record_outcome(
        registry,
        hypothesis,
        "dataset-full-content-fingerprint",
        factory_status,
        reason,
        metrics,
    )

    assert experiment_id == "hyp_eval"
    rows = registry.all_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "hyp_eval"
    assert row["status"] == factory_status.lower()
    assert row["hypothesis"] == hypothesis.proposed_mechanism
    assert row["dataset_fingerprint"] == "dataset-full-content-fingerprint"
    assert row["config_fingerprint"] == config_fingerprint(_PARAMS)
    assert row["rejection_reason"] == reason
    assert json.loads(row["params_json"]) == _PARAMS
    assert json.loads(row["provenance_json"]) == {
        "factory_status": factory_status,
        "reason": reason,
        "canonical_hypothesis": hypothesis.to_dict(),
    }
    assert row["metrics"] == (metrics or {})
    if metrics is None:
        assert row["wr"] is None
        assert row["expectancy"] is None
        assert row["profit_factor"] is None
        assert row["max_drawdown_pct"] is None
        assert row["tail_loss"] is None
        assert row["n_trades"] is None


def test_record_outcome_surfaces_duplicate_registry_error(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    hypothesis = _hypothesis()
    record_outcome(registry, hypothesis, "dataset-a", "FAILED", "first failure")

    with pytest.raises(DuplicateExperimentError, match="already recorded"):
        record_outcome(registry, hypothesis, "dataset-a", "FAILED", "retry")


def test_record_outcome_surfaces_equivalent_registry_error(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    record_outcome(
        registry,
        _hypothesis("hyp_rejected"),
        "dataset-a",
        "REJECTED",
        "failed governed gates",
    )

    with pytest.raises(EquivalentExperimentError, match="equivalent rejected"):
        record_outcome(
            registry,
            _hypothesis("hyp_equivalent"),
            "dataset-a",
            "CHALLENGER",
            "unjustified retry",
        )


def test_sealed_evaluation_is_callback_owned_and_persistent_after_restart(
    tmp_path: Path,
):
    frozen = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2, "side": "buy"},
        artifact_hash="model-a",
    )
    path = tmp_path / "sealed.jsonl"
    callback_candidates = []

    def evaluate(candidate):
        callback_candidates.append(candidate)
        assert not hasattr(candidate, "sealed_holdout")
        return {"expectancy": 0.2, "n_trades": 25}

    first = evaluate_candidate_once(
        frozen,
        SealedHoldoutStore(path),
        "holdout-a",
        evaluate,
    )

    assert callback_candidates == [frozen]
    assert first["frozen_hash"] == frozen.frozen_hash
    assert first["holdout_fingerprint"] == "holdout-a"
    assert first["metrics"] == {"expectancy": 0.2, "n_trades": 25}

    with pytest.raises(SealedHoldoutError, match="already scored"):
        evaluate_candidate_once(
            frozen,
            SealedHoldoutStore(path),
            "holdout-a",
            evaluate,
        )
    assert callback_candidates == [frozen]


def test_sealed_evaluation_requires_frozen_candidate_before_callback(tmp_path: Path):
    called = False

    def evaluate(candidate):
        nonlocal called
        called = True
        return {}

    with pytest.raises(TypeError, match="FrozenCandidate"):
        evaluate_candidate_once(
            {"strategy_id": "not-frozen"},
            SealedHoldoutStore(tmp_path / "sealed.jsonl"),
            "holdout-a",
            evaluate,
        )
    assert called is False


def test_factory_generation_terminal_outcome_is_persisted_without_zero_metrics(
    tmp_path: Path,
):
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=7, dataset_fingerprint="canonical-data-a")
    factory.experiment_registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    factory._log_event = lambda *args, **kwargs: None

    factory._record_generation_outcome("NO_DATA", "no matured samples")

    assert factory.state.last_generation_status == "NO_DATA"
    assert factory.state.last_generation_reason == "no matured samples"
    rows = factory.experiment_registry.all_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "research_factory_generation_7"
    assert row["status"] == "no_data"
    assert row["dataset_fingerprint"] == "canonical-data-a"
    assert row["rejection_reason"] == "no matured samples"
    assert row["metrics"] == {}
    assert row["expectancy"] is None
    assert row["n_trades"] is None
