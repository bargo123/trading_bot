"""Causal prediction evidence fusion for the rapid Firehose.

The calibrated executable model owns probability and the final prediction
decision.  Book/Watcher evidence is retained as attributable, read-only
context and may only break ranking ties or explain a candidate.  It can never
create probability, override an abstention, or grant broker authority.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from aegis.research.external_dag.catalog import REQUIRED_EXTERNAL_TOOLS
from aegis.research.external_dag.contracts import content_hash
from aegis.research.watcher_algorithms import ALGORITHM_MODULES
from aegis.intel.watcher_advisory import book_feature_snapshot


_EXPECTED_BOOK_REGISTRY_HASH = content_hash(tuple(ALGORITHM_MODULES))
_EXPECTED_RESEARCH_TOOLS = frozenset(REQUIRED_EXTERNAL_TOOLS) | {
    "aegis-book-algorithms"
}
_PREDICTION_SCOPE = "GITHUB_TOOLS_AND_BOOK_ALGORITHMS_ONLY"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _safe_count(value: Any) -> int:
    number = _finite(value)
    return int(number) if number is not None and number.is_integer() and number >= 0 else 0

def _model_scope_allowed(model: Mapping[str, Any] | None) -> bool:
    """Reject model evidence explicitly produced by excluded research lanes."""
    if not isinstance(model, Mapping):
        return True
    sources: list[Mapping[str, Any]] = [model]
    bundle = model.get("execution_bundle")
    if isinstance(bundle, Mapping):
        sources.append(bundle)
    for source in sources:
        if source.get("council_influence") is True:
            return False
        if source.get("research_factory_influence") is True:
            return False
        declared_scope = str(source.get("prediction_scope") or "").strip()
        if declared_scope and declared_scope != _PREDICTION_SCOPE:
            return False
    return True


def _book_score(
    book: Mapping[str, Any] | None,
    *,
    side: str | None = None,
) -> tuple[float | None, str, dict[str, Any]]:
    if not isinstance(book, Mapping):
        return None, "UNAVAILABLE", {}
    if (
        str(book.get("status") or "").upper() not in {"AVAILABLE", ""}
        or book.get("execution_authority") is not False
        or book.get("research_only") is not True
        or book.get("no_lookahead") is not True
    ):
        return None, "UNAVAILABLE", {}
    absolute_views = bool(book.get("absolute_views", False))
    explicit = _finite(book.get("directional_support_ratio"))
    if absolute_views:
        explicit = None
    supporting = _finite(book.get("supporting_count"))
    opposing = _finite(book.get("opposing_count"))
    if supporting is None and isinstance(book.get("supporting_algorithms"), (list, tuple)):
        supporting = float(len(book["supporting_algorithms"]))
    if opposing is None and isinstance(book.get("opposing_algorithms"), (list, tuple)):
        opposing = float(len(book["opposing_algorithms"]))
    if absolute_views and str(side or "").upper() == "SELL":
        supporting, opposing = opposing, supporting
    score = explicit
    if score is None and supporting is not None and opposing is not None:
        total = supporting + opposing
        if total > 0 and supporting >= 0 and opposing >= 0:
            score = supporting / total
    if score is None or not 0.0 <= score <= 1.0:
        return None, "UNAVAILABLE", {}
    if score > 0.5:
        status = "SUPPORTING"
    elif score < 0.5:
        status = "OPPOSING"
    else:
        status = "MIXED"
    return round(score, 6), status, {
        "algorithm_count": _safe_count(book.get("algorithm_count")),
        "supporting_count": _safe_count(supporting),
        "opposing_count": _safe_count(opposing),
        "algorithm_result_sha256": str(
            book.get("algorithm_result_sha256") or book.get("artifact_hash") or ""
        ),
    }


def fuse_prediction_evidence(
    model: Mapping[str, Any] | None,
    *,
    book_context: Mapping[str, Any] | None = None,
    research_provenance: Mapping[str, Any] | None = None,
    symbol: str | None = None,
    side: str | None = None,
    mechanism: str | None = None,
    horizon_s: int | None = None,
) -> dict[str, Any]:
    """Fuse validated model output with bounded book context.

    ``probability`` and ``decision`` are copied from the model only after the
    model has a calibrated, positive after-cost executable result.  Book
    support is a secondary rank/explanation feature and is never substituted
    for missing model evidence.
    """
    probability = _finite(model.get("probability", model.get("p_captured_win"))) if isinstance(model, Mapping) else None
    lcb95 = _finite(model.get("p_captured_win_lcb95", model.get("expected_net_pnl_lcb95"))) if isinstance(model, Mapping) else None
    expected = _finite(model.get("expected_net_pnl")) if isinstance(model, Mapping) else None
    threshold = _finite(model.get("threshold")) if isinstance(model, Mapping) else None
    calibrated = (
        isinstance(model, Mapping)
        and _model_scope_allowed(model)
        and str(model.get("calibration_status") or "").upper() == "CALIBRATED"
        and probability is not None
        and 0.0 <= probability <= 1.0
        and threshold is not None
        and 0.0 < threshold < 1.0
        and expected is not None
        and expected > 0.0
        and lcb95 is not None
        and lcb95 > 0.0
        and bool(model.get("decision"))
    )
    score, book_status, book_details = _book_score(book_context, side=side)
    book_features = book_feature_snapshot(book_context, candidate_side=side)
    rank_score = (
        float(book_features["book_rank_score"])
        if book_features.get("book_available") == 1.0
        else None
    )
    book_details = {**book_details, "features": book_features}
    nodes = research_provenance.get("nodes") if isinstance(research_provenance, Mapping) else None
    if not isinstance(nodes, (list, tuple)) or not nodes:
        external_status = "UNAVAILABLE"
        external_count = 0
    elif any(
        not isinstance(node, Mapping) or node.get("execution_authority") is not False
        for node in nodes
    ):
        external_status = "INVALID"
        external_count = len(nodes)
    else:
        tool_ids = [str(node.get("tool_id") or "").strip() for node in nodes]
        expected_tools = _EXPECTED_RESEARCH_TOOLS
        registry_hash = str(research_provenance.get("book_registry_hash") or "").lower()
        if (
            set(tool_ids) != expected_tools
            or len(tool_ids) != len(expected_tools)
        ):
            external_status = "INCOMPLETE"
        elif registry_hash != _EXPECTED_BOOK_REGISTRY_HASH:
            external_status = "INVALID"
        elif all(str(node.get("status") or "").upper() == "SUCCESS" for node in nodes):
            external_status = "COMPLETE"
        else:
            external_status = "INCOMPLETE"
        external_count = len(nodes)
    result: dict[str, Any] = {
        "prediction_scope": _PREDICTION_SCOPE,
        "council_influence": False,
        "research_factory_influence": False,
        "status": "AVAILABLE" if calibrated else "ABSTAIN",
        "reason": "model_eligible" if calibrated else (
            "validated_model_missing" if not isinstance(model, Mapping)
            else "model_scope_excluded" if not _model_scope_allowed(model)
            else "model_not_execution_ready"
        ),
        "probability": probability,
        "probability_lcb95": lcb95,
        "expected_net_pnl": expected,
        "threshold": threshold,
        "decision": bool(calibrated),
        "book_support_score": score,
        "book_rank_score": rank_score,
        "book_evidence_status": book_status,
        "book_is_secondary": True,
        "book_evidence": book_details,
        "external_research_status": external_status,
        "external_research_node_count": external_count,
        "candidate_identity": {
            "symbol": str(symbol or "").upper(),
            "side": str(side or "").lower(),
            "mechanism": str(mechanism or ""),
            "horizon_s": int(horizon_s) if horizon_s is not None else None,
        },
        "execution_authority": False,
        "research_only": True,
    }
    if isinstance(model, Mapping):
        execution_bundle = model.get("execution_bundle")
        if isinstance(execution_bundle, Mapping):
            result["model_provenance"] = {
                key: execution_bundle.get(key)
                for key in (
                    "execution_bundle_hash",
                    "research_bundle_hash",
                    "dataset_hash",
                    "validation_hash",
                    "model_artifact_hash",
                    "target_definition",
                )
                if execution_bundle.get(key) is not None
            }
    return result


__all__ = ["fuse_prediction_evidence"]
