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
    OutcomePersistenceConflictError,
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
    ("factory_status", "registry_status", "metrics"),
    [
        ("NO_DATA", "failed", None),
        ("NO_EVIDENCE", "failed", None),
        ("NOT_EXECUTABLE", "failed", None),
        ("FAILED", "failed", None),
        ("REJECTED", "rejected", {"expectancy": -0.25, "n_trades": 4}),
        ("CHALLENGER", "accepted", {"expectancy": 0.4, "n_trades": 24}),
    ],
)
def test_record_outcome_persists_every_terminal_status_without_fabricated_metrics(
    tmp_path: Path,
    factory_status: str,
    registry_status: str,
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
    assert row["status"] == registry_status
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


def test_record_outcome_persists_duplicate_as_unique_failed_conflict(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    hypothesis = _hypothesis()
    record_outcome(registry, hypothesis, "dataset-a", "FAILED", "first failure")

    with pytest.raises(OutcomePersistenceConflictError) as caught:
        record_outcome(registry, hypothesis, "dataset-a", "FAILED", "retry")
    rows = registry.all_rows()
    assert len(rows) == 2
    conflict = registry.get(caught.value.conflict_id)
    assert conflict is not None
    assert conflict["id"] != "hyp_eval"
    assert conflict["status"] == "failed"
    provenance = json.loads(conflict["provenance_json"])
    assert provenance["persistence_conflict"] == {
        "attempted_id": "hyp_eval",
        "attempted_factory_status": "FAILED",
        "attempted_identity": {
            "config_fingerprint": config_fingerprint(_PARAMS),
            "dataset_fingerprint": "dataset-a",
            "hypothesis": hypothesis.proposed_mechanism,
        },
        "error_type": DuplicateExperimentError.__name__,
        "error": "experiment id 'hyp_eval' already recorded; mint a new id",
    }


def test_record_outcome_persists_equivalent_as_unique_failed_conflict(tmp_path: Path):
    registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    record_outcome(
        registry,
        _hypothesis("hyp_rejected"),
        "dataset-a",
        "REJECTED",
        "failed governed gates",
    )

    with pytest.raises(OutcomePersistenceConflictError) as caught:
        record_outcome(
            registry,
            _hypothesis("hyp_equivalent"),
            "dataset-a",
            "CHALLENGER",
            "unjustified retry",
        )
    conflict = registry.get(caught.value.conflict_id)
    assert conflict is not None
    assert conflict["status"] == "failed"
    assert conflict["new_reason"]
    provenance = json.loads(conflict["provenance_json"])
    assert provenance["persistence_conflict"]["attempted_id"] == "hyp_equivalent"
    assert provenance["persistence_conflict"]["error_type"] == (
        EquivalentExperimentError.__name__
    )


def test_sealed_evaluation_is_callback_owned_and_persistent_after_restart(
    tmp_path: Path,
):
    frozen = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2, "side": "buy"},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-a",
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
    assert first["training_dataset_fingerprint"] == "training-a"
    assert first["metrics"] == {"expectancy": 0.2, "n_trades": 25}

    with pytest.raises(SealedHoldoutError, match="already reserved"):
        evaluate_candidate_once(
            frozen,
            SealedHoldoutStore(path),
            "holdout-a",
            evaluate,
        )
    assert callback_candidates == [frozen]


def test_frozen_identity_is_deterministic_and_includes_training_dataset():
    first = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2, "side": "buy"},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-a",
    )
    same_identity = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"side": "buy", "window": 2},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-a",
    )
    different_training_data = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2, "side": "buy"},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-b",
    )

    assert first.frozen_hash == same_identity.frozen_hash
    assert first.frozen_hash != different_training_data.frozen_hash
    assert first.training_dataset_fingerprint == "training-a"
    assert first.as_dict()["training_dataset_fingerprint"] == "training-a"


@pytest.mark.parametrize("fingerprint", [None, "", "   "])
def test_freeze_candidate_requires_observed_training_fingerprint(fingerprint):
    with pytest.raises(ValueError, match="training_dataset_fingerprint"):
        freeze_candidate(
            strategy_id="breakout-v1",
            code_hash="code-a",
            config={"window": 2},
            artifact_hash="model-a",
            training_dataset_fingerprint=fingerprint,
        )


def test_sealed_callback_failure_consumes_key_and_persists_terminal_failure(
    tmp_path: Path,
):
    frozen = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-a",
    )
    path = tmp_path / "sealed.jsonl"
    calls = 0

    def fail(candidate):
        nonlocal calls
        calls += 1
        raise RuntimeError("evaluator crashed")

    with pytest.raises(RuntimeError, match="evaluator crashed"):
        evaluate_candidate_once(frozen, SealedHoldoutStore(path), "holdout-a", fail)

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["reserved", "failed"]
    assert rows[0]["record_type"] == "reservation"
    assert rows[1]["error"]["type"] == "RuntimeError"
    assert rows[1]["error"]["message"] == "evaluator crashed"
    assert "metrics" not in rows[1]

    with pytest.raises(SealedHoldoutError, match="already reserved"):
        evaluate_candidate_once(frozen, SealedHoldoutStore(path), "holdout-a", fail)
    assert calls == 1


def test_sealed_result_normalization_failure_persists_terminal_failure(tmp_path: Path):
    frozen = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-a",
    )
    path = tmp_path / "sealed.jsonl"

    with pytest.raises(TypeError):
        evaluate_candidate_once(
            frozen,
            SealedHoldoutStore(path),
            "holdout-a",
            lambda candidate: {"metrics": {}, "pnls": 1},
        )

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["status"] for row in rows] == ["reserved", "failed"]
    assert rows[1]["error"]["type"] == "TypeError"


def test_preexisting_sealed_reservation_blocks_callback(tmp_path: Path):
    frozen = freeze_candidate(
        strategy_id="breakout-v1",
        code_hash="code-a",
        config={"window": 2},
        artifact_hash="model-a",
        training_dataset_fingerprint="training-a",
    )
    path = tmp_path / "sealed.jsonl"
    path.write_text(
        json.dumps(
            {
                "record_type": "reservation",
                "status": "reserved",
                "frozen_hash": frozen.frozen_hash,
                "holdout_fingerprint": "holdout-a",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    called = False

    def evaluate(candidate):
        nonlocal called
        called = True
        return {}

    with pytest.raises(SealedHoldoutError, match="already reserved"):
        evaluate_candidate_once(
            frozen,
            SealedHoldoutStore(path),
            "holdout-a",
            evaluate,
        )
    assert called is False


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
    assert row["status"] == "failed"
    assert row["dataset_fingerprint"] == "canonical-data-a"
    assert row["rejection_reason"] == "no matured samples"
    assert row["metrics"] == {}
    assert row["expectancy"] is None
    assert row["n_trades"] is None


def test_factory_terminal_persistence_requires_registry():
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=7, dataset_fingerprint="canonical-data-a")
    factory._log_event = lambda *args, **kwargs: None

    with pytest.raises(RuntimeError, match="ExperimentRegistry.*required"):
        factory._record_generation_outcome("NO_DATA", "no matured samples")

    assert factory.state.last_generation_status == "FAILED"
    assert "registry" in factory.state.last_generation_reason.lower()


def test_factory_conflict_sets_failed_state_and_persists_conflict(tmp_path: Path):
    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=7, dataset_fingerprint="canonical-data-a")
    factory.experiment_registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    factory._log_event = lambda *args, **kwargs: None
    factory._record_generation_outcome("NO_DATA", "first attempt")

    with pytest.raises(OutcomePersistenceConflictError) as caught:
        factory._record_generation_outcome("NO_DATA", "duplicate attempt")

    assert factory.state.last_generation_status == "FAILED"
    assert caught.value.conflict_id in factory.state.last_generation_reason
    rows = factory.experiment_registry.all_rows()
    assert [row["status"] for row in rows] == ["failed", "failed"]


def test_generation_clears_stale_dataset_fingerprint_before_early_outcome(
    monkeypatch,
    tmp_path: Path,
):
    class EmptyDataPipeline:
        def load_sources(self, sources):
            return type("EmptyFrame", (), {"empty": True})()

    factory = object.__new__(ResearchFactory)
    factory.state = ResearchState(generation=8, dataset_fingerprint="prior-generation")
    factory.source_roots = (Path("unused"),)
    factory.data_pipeline = EmptyDataPipeline()
    factory.experiment_registry = ExperimentRegistry(tmp_path / "experiments.sqlite")
    factory._log_event = lambda *args, **kwargs: None
    monkeypatch.setattr(
        "aegis.research_factory.core.discover_csv_sources", lambda roots: []
    )

    factory._run_generation()

    assert factory.state.dataset_fingerprint == "NOT_COMPUTED"
    row = factory.experiment_registry.all_rows()[0]
    assert row["dataset_fingerprint"] == "NOT_COMPUTED"
