"""Governed persistence and sealed evaluation boundaries for the factory."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from aegis.research.fingerprint import config_fingerprint
from aegis.research.registry import ExperimentRegistry
from aegis.research.sealed import FrozenCandidate, SealedHoldoutStore
from aegis.research_factory.hypothesis import Hypothesis


TERMINAL_STATUSES = frozenset(
    {"NO_DATA", "NO_EVIDENCE", "NOT_EXECUTABLE", "FAILED", "REJECTED", "CHALLENGER"}
)

_PARAMETER_FIELDS = (
    "features_required",
    "entry_rule",
    "exit_rule",
    "side",
    "entry_price",
    "invalidation_price",
    "target_price",
    "max_hold_s",
)


def _canonical_hypothesis(hypothesis: Hypothesis | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(hypothesis, Hypothesis):
        return hypothesis.to_dict()
    if isinstance(hypothesis, Mapping):
        return dict(hypothesis)
    raise TypeError("hypothesis must be a canonical Hypothesis or mapping")


def record_outcome(
    registry: ExperimentRegistry,
    hypothesis: Hypothesis | Mapping[str, Any],
    dataset_fingerprint: str,
    status: str,
    reason: str,
    metrics: Mapping[str, Any] | None = None,
) -> str:
    """Persist one honest terminal factory outcome through the governed registry."""
    factory_status = str(status)
    if factory_status not in TERMINAL_STATUSES:
        raise ValueError(f"unsupported factory terminal status: {factory_status}")
    canonical = _canonical_hypothesis(hypothesis)
    experiment_id = str(canonical.get("hypothesis_id") or "").strip()
    if not experiment_id:
        raise ValueError("hypothesis_id is required to record an outcome")
    mechanism = str(canonical.get("proposed_mechanism") or "").strip()
    if not mechanism:
        raise ValueError("proposed_mechanism is required to record an outcome")
    observed_metrics = dict(metrics) if metrics is not None else {}
    params = {
        field: canonical[field]
        for field in _PARAMETER_FIELDS
        if field in canonical
    }
    row: dict[str, Any] = {
        "id": experiment_id,
        "hypothesis": mechanism,
        "status": factory_status.lower(),
        "config_fingerprint": config_fingerprint(params),
        "dataset_fingerprint": str(dataset_fingerprint),
        "provenance": {
            "factory_status": factory_status,
            "reason": str(reason),
            "canonical_hypothesis": canonical,
        },
        "params": params,
        "metrics": observed_metrics,
        "rejection_reason": str(reason),
    }
    for field in (
        "win_rate",
        "expectancy",
        "profit_factor",
        "max_drawdown_pct",
        "tail_loss",
        "n_trades",
    ):
        if field in observed_metrics:
            row[field] = observed_metrics[field]
    return registry.record(row)


def evaluate_candidate_once(
    candidate: FrozenCandidate,
    sealed_store: SealedHoldoutStore,
    holdout_fingerprint: str,
    evaluate: Callable[[FrozenCandidate], Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate an already frozen candidate only inside the persistent sealed store."""
    if not isinstance(candidate, FrozenCandidate):
        raise TypeError("candidate must be a FrozenCandidate before sealed evaluation")
    return sealed_store.evaluate_once(
        candidate,
        holdout_fingerprint=str(holdout_fingerprint),
        evaluate=lambda: evaluate(candidate),
    )
