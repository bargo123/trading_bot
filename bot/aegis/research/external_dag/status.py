"""Atomic, read-only status projection for external research workflows."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .bundles import ExecutionBundle, PromotionDecision
from .contracts import ResearchBundle, canonical_json


def project_status(
    research_bundle: ResearchBundle,
    *,
    promotion: PromotionDecision,
    execution_bundle: ExecutionBundle | None,
) -> dict[str, Any]:
    book_result = next(
        (
            result
            for result in research_bundle.node_results
            if result.tool_id == "aegis-book-algorithms"
        ),
        None,
    )
    external_results = tuple(
        result
        for result in research_bundle.node_results
        if result.tool_id != "aegis-book-algorithms"
    )
    input_results = tuple(
        result
        for result in research_bundle.node_results
        if bool(
            result.payload.get(
                "input_contract_applicable",
                result.tool_id != "aegis-book-algorithms",
            )
        )
    )
    selected_ids = tuple(
        str(value)
        for result in external_results
        for value in (result.payload.get("selected_strategy_ids") or ())
    )
    selected_ids = tuple(dict.fromkeys(selected_ids))
    domain_results = tuple(
        result for result in external_results if "domain_artifact_verified" in result.payload
    )
    return {
        "schema": "aegis.external_dag_status.v1",
        "prediction_scope": "GITHUB_TOOLS_AND_BOOK_ALGORITHMS_ONLY",
        "execution_authority": False,
        "research_only": True,
        "order_intent": False,
        "council_influence": False,
        "research_factory_influence": False,
        "workflow_id": research_bundle.workflow_id,
        "run_id": research_bundle.run_id,
        "complete": research_bundle.complete,
        "research_bundle_hash": research_bundle.bundle_hash,
        "promotion_status": promotion.status,
        "promotion_reasons": list(promotion.reasons),
        "execution_bundle_hash": (
            execution_bundle.bundle_hash if execution_bundle is not None else None
        ),
        "external_input_node_count": len(external_results),
        "external_input_verified_count": sum(
            bool(result.payload.get("input_artifacts_verified"))
            for result in external_results
        ),
        "external_input_consumed_count": sum(
            bool(result.payload.get("input_consumed"))
            for result in external_results
        ),
        "input_contract_node_count": len(input_results),
        "input_contract_verified_count": sum(
            bool(result.payload.get("input_artifacts_verified"))
            for result in input_results
        ),
        "input_contract_consumed_count": sum(
            bool(result.payload.get("input_consumed"))
            for result in input_results
        ),
        "selected_strategy_ids": list(selected_ids),
        "selected_strategy_count": len(selected_ids),
        "domain_artifact_node_count": len(domain_results),
        "domain_artifact_verified_count": sum(
            bool(result.payload.get("domain_artifact_verified"))
            for result in domain_results
        ),
        "book_algorithm_count": (
            int(book_result.payload.get("algorithm_count") or 0)
            if book_result is not None else 0
        ),
        "nodes": [
            {
                "node_id": result.node_id,
                "tool_id": result.tool_id,
                "status": result.status,
                "reason": result.reason,
                "duration_ms": round(result.duration_ms, 3),
                "artifact_hashes": list(result.artifact_hashes),
                "execution_authority": False,
                "research_only": True,
                "order_intent": False,
                "input_contract_applicable": bool(
                    result.payload.get(
                        "input_contract_applicable",
                        result.tool_id != "aegis-book-algorithms",
                    )
                ),
                "input_artifacts_verified": bool(
                    result.payload.get("input_artifacts_verified", False)
                ),
                "input_consumed": bool(result.payload.get("input_consumed", False)),
                "input_manifest_hash": result.payload.get("input_manifest_hash"),
                "input_dataset_schema": result.payload.get("input_dataset_schema"),
                "input_state_field_count": int(
                    result.payload.get("input_state_field_count") or 0
                ),
                "selected_strategy_ids": list(
                    result.payload.get("selected_strategy_ids") or ()
                ),
                "selected_strategy_count": int(
                    result.payload.get("selected_strategy_count") or 0
                ),
                "domain_artifact_verified": bool(
                    result.payload.get("domain_artifact_verified", False)
                ),
                "domain_artifact_schema": result.payload.get("domain_artifact_schema"),
                "domain_artifact_tool": result.payload.get("domain_artifact_tool"),
                "domain_artifact_operation": result.payload.get(
                    "domain_artifact_operation"
                ),
                "domain_artifact_strategy_count": int(
                    result.payload.get("domain_artifact_strategy_count") or 0
                ),
            }
            for result in research_bundle.node_results
        ],
    }


def write_status_atomic(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(canonical_json(dict(payload)))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["project_status", "write_status_atomic"]
