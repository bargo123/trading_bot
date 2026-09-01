"""One governed workflow connecting the installed external research roles."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from aegis.research.registry import ExperimentRegistry
from aegis.research.watcher_algorithms import ALGORITHM_MODULES

from .adapters import BookAlgorithmAdapter, ResearchAdapter, build_adapter_registry
from .bundles import (
    ExecutionBundle,
    PromotionDecision,
    assess_execution_readiness,
    build_execution_bundle,
)
from .contracts import (
    ExternalTaskResult,
    ResearchBundle,
    WorkflowNodeSpec,
    WorkflowSpec,
    canonical_json,
    content_hash,
)
from .scheduler import ExternalDagRunner
from .status import project_status, write_status_atomic
from .store import ArtifactStore


WORKFLOW_ID = "full_research_validation.v1"


def book_context_from_result(
    result: ExternalTaskResult,
    store: ArtifactStore,
) -> dict[str, Any]:
    """Compile the sealed book artifact into read-only prediction context."""
    if (
        result.tool_id != "aegis-book-algorithms"
        or result.status != "SUCCESS"
        or len(result.artifact_hashes) != 1
    ):
        raise ValueError("book result is unavailable")
    artifact = store.get(result.artifact_hashes[0])
    if (
        artifact.producer != "aegis-book-algorithms"
        or artifact.schema != "aegis.book_algorithm_results.v1"
    ):
        raise ValueError("book artifact schema is invalid")
    expected_registry_hash = content_hash(tuple(ALGORITHM_MODULES))
    if str(artifact.provenance.get("registry_hash") or "").lower() != expected_registry_hash:
        raise ValueError("book artifact registry mismatch")
    payload = artifact.payload
    rows = payload.get("algorithms") if isinstance(payload, Mapping) else None
    algorithm_ids = tuple(str(value) for value in payload.get("algorithm_ids") or ()) if isinstance(payload, Mapping) else ()
    try:
        algorithm_count = int(payload.get("algorithm_count") or 0)
    except (TypeError, ValueError, OverflowError):
        algorithm_count = 0
    if (
        not isinstance(rows, (list, tuple))
        or len(rows) != len(ALGORITHM_MODULES)
        or len(algorithm_ids) != len(ALGORITHM_MODULES)
        or algorithm_count != len(ALGORITHM_MODULES)
    ):
        raise ValueError("book artifact coverage is incomplete")
    if set(algorithm_ids) != set(ALGORITHM_MODULES) or len(set(algorithm_ids)) != len(algorithm_ids):
        raise ValueError("book artifact registry mismatch")
    if (
        payload.get("execution_authority") is not False
        or payload.get("research_only") is not True
        or payload.get("order_intent") is not False
        or payload.get("no_lookahead") is not True
    ):
        raise ValueError("book artifact contract is invalid")
    supporting: list[str] = []
    opposing: list[str] = []
    missing: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("book artifact row is invalid")
        algorithm_id = str(row.get("algorithm_id") or "")
        view = str(row.get("view") or "").upper()
        applicability = str(row.get("applicability") or "").upper()
        if (
            algorithm_id not in set(ALGORITHM_MODULES)
            or row.get("execution_authority") is not False
            or row.get("research_only") is not True
            or row.get("uses_future_data") is not False
        ):
            raise ValueError("book artifact row contract is invalid")
        if applicability == "APPLICABLE" and view == "BUY":
            supporting.append(algorithm_id)
        elif applicability == "APPLICABLE" and view == "SELL":
            opposing.append(algorithm_id)
        else:
            missing.append(algorithm_id)
    return {
        "status": "AVAILABLE",
        "algorithm_count": len(algorithm_ids),
        "algorithm_ids": list(algorithm_ids),
        "state_hash": str(payload.get("state_hash") or ""),
        "decision_ts": payload.get("decision_ts"),
        "artifact_hash": str(result.artifact_hashes[0]),
        "book_registry_hash": str(artifact.provenance.get("registry_hash") or ""),
        "evaluated_count": len(rows),
        "applicable_count": len(supporting) + len(opposing),
        "supporting_algorithms": supporting,
        "opposing_algorithms": opposing,
        "missing_data_algorithms": missing,
        "supporting_count": len(supporting),
        "opposing_count": len(opposing),
        "missing_data_algorithm_count": len(missing),
        "missing_data_count": len(missing),
        "algorithm_result_sha256": str(result.artifact_hashes[0]),
        "absolute_views": True,
        "compiled_from_artifact": True,
        "execution_authority": False,
        "research_only": True,
        "no_lookahead": payload.get("no_lookahead") is True,
        "order_intent": False,
    }


def build_full_research_workflow() -> WorkflowSpec:
    nodes: list[WorkflowNodeSpec] = [
        WorkflowNodeSpec("source-catalog", "awesome-systematic-trading", "awesome-systematic-trading"),
        WorkflowNodeSpec("book-algorithms", "aegis-book-algorithms", "aegis-book-algorithms"),
        WorkflowNodeSpec("offline-model", "qlib", "qlib", ("source-catalog", "book-algorithms")),
        WorkflowNodeSpec("order-replay", "ordersim", "ordersim", ("offline-model",)),
        WorkflowNodeSpec("tick-replay", "hftbacktest", "hftbacktest", ("offline-model",)),
        WorkflowNodeSpec("chronological-oos", "oos-lab", "oos-lab", ("order-replay", "tick-replay")),
        WorkflowNodeSpec("methodology-review", "Keystone", "Keystone", ("chronological-oos",)),
        WorkflowNodeSpec(
            "research-integrity",
            "algorithmic-trading-research-framework",
            "algorithmic-trading-research-framework",
            ("chronological-oos",),
        ),
        WorkflowNodeSpec("recovery-model", "samvid-trading-core", "samvid-trading-core", ("order-replay", "tick-replay")),
        WorkflowNodeSpec("mt5-contract-reference", "Vibe-Trading", "Vibe-Trading", ("source-catalog",)),
        WorkflowNodeSpec(
            "mt5-read-only-diagnostics",
            "metatrader5-mcp-server",
            "metatrader5-mcp-server",
            ("mt5-contract-reference",),
        ),
        WorkflowNodeSpec("nautilus-parity", "nautilus_trader", "nautilus_trader", ("order-replay", "tick-replay")),
        WorkflowNodeSpec("lean-parity", "Lean", "Lean", ("order-replay", "tick-replay")),
        WorkflowNodeSpec("latency-stress", "abides", "abides", ("order-replay", "tick-replay")),
    ]
    all_research_nodes = tuple(node.node_id for node in nodes)
    nodes.append(
        WorkflowNodeSpec(
            "control-plane-status",
            "OpenAlice",
            "OpenAlice",
            all_research_nodes,
            allow_failed_dependencies=True,
        )
    )
    return WorkflowSpec(WORKFLOW_ID, tuple(nodes))


@dataclass(frozen=True)
class WorkflowOutcome:
    research_bundle: ResearchBundle
    promotion: PromotionDecision
    execution_bundle: ExecutionBundle | None


def _selected_strategy_context(evidence: Mapping[str, Any]) -> tuple[tuple[str, ...], Mapping[str, Any]]:
    """Return the bounded strategy set that external domain nodes may run."""
    raw_ids = evidence.get("selected_strategy_ids")
    if raw_ids is None:
        selection = evidence.get("algorithm_selection")
        if isinstance(selection, Mapping):
            raw_ids = selection.get("selected_algorithm_ids")
    if raw_ids is None:
        return (), {}
    if not isinstance(raw_ids, (list, tuple)):
        raise ValueError("selected_strategy_ids must be a list")
    ids = tuple(str(value).strip() for value in raw_ids)
    if not 1 <= len(ids) <= 10 or any(not value for value in ids):
        raise ValueError("selected_strategy_ids must contain 1 to 10 non-empty ids")
    if len(set(ids)) != len(ids):
        raise ValueError("selected_strategy_ids must be unique")
    raw_metrics = evidence.get("selected_strategy_metrics")
    if raw_metrics is None:
        selection = evidence.get("algorithm_selection")
        if isinstance(selection, Mapping):
            raw_metrics = selection.get("selected_metrics")
    metrics = dict(raw_metrics) if isinstance(raw_metrics, Mapping) else {}
    return ids, metrics


def _write_execution_bundle_atomic(path: Path, bundle: ExecutionBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(canonical_json(bundle.as_dict()))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execute_research_workflow(
    *,
    project_root: Path,
    dataset_manifest_path: Path,
    run_id: str,
    artifact_root: Path,
    registry_path: Path,
    status_path: Path,
    execution_bundle_path: Path,
    adapters: Mapping[str, ResearchAdapter] | None = None,
    max_workers: int = 4,
    timeout_s: float = 60.0,
) -> WorkflowOutcome:
    manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise ValueError("dataset manifest root must be an object")
    state = manifest.get("point_in_time_state")
    if not isinstance(state, Mapping):
        raise ValueError("dataset manifest requires point_in_time_state")
    evidence = manifest.get("validation_evidence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    else:
        evidence = dict(evidence)
    selected_strategy_ids, selected_strategy_metrics = _selected_strategy_context(evidence)
    dataset_manifest_hash = content_hash(manifest)

    adapter_registry = (
        dict(adapters)
        if adapters is not None
        else build_adapter_registry(project_root, timeout_s=timeout_s)
    )
    adapter_registry.setdefault("aegis-book-algorithms", BookAlgorithmAdapter())
    workflow = build_full_research_workflow()
    store = ArtifactStore(artifact_root)
    dataset_artifact = store.put(
        producer="aegis-dataset-manifest",
        schema="aegis.frozen_dataset_manifest.v1",
        payload=manifest,
        provenance={
            "manifest_hash": dataset_manifest_hash,
            "source_path": str(dataset_manifest_path.resolve()),
        },
    )
    parameters = {
        node.node_id: {
            "dataset_manifest_hash": dataset_manifest_hash,
            "_dataset_artifact_hash": dataset_artifact.content_hash,
            "state": dict(state),
            "selected_strategy_ids": selected_strategy_ids,
            "selected_strategy_metrics": selected_strategy_metrics,
        }
        for node in workflow.nodes
    }
    research_bundle = ExternalDagRunner(
        adapters=adapter_registry,
        store=store,
        max_workers=max_workers,
    ).run(workflow, run_id=run_id, parameters_by_node=parameters)
    book_result = next(
        (row for row in research_bundle.node_results if row.node_id == "book-algorithms"),
        None,
    )
    derived_book_context: dict[str, Any] | None = None
    if book_result is not None and book_result.status == "SUCCESS":
        try:
            derived_book_context = book_context_from_result(book_result, store)
        except (OSError, TypeError, ValueError):
            derived_book_context = None
    if derived_book_context is not None:
        declared = evidence.get("book_context")
        if isinstance(declared, Mapping):
            derived_book_context["declared_context"] = dict(declared)
        evidence["book_context"] = derived_book_context
        evidence.setdefault(
            "book_registry_hash", derived_book_context["book_registry_hash"]
        )
        evidence.setdefault(
            "book_algorithm_count", derived_book_context["algorithm_count"]
        )
    else:
        # Never let a manifest-supplied label stand in for a failed or missing
        # artifact compilation.
        evidence["book_context"] = {}
    promotion = assess_execution_readiness(research_bundle, evidence)
    execution_bundle = (
        build_execution_bundle(research_bundle, evidence)
        if promotion.authorized else None
    )
    ExperimentRegistry(registry_path).record_external_workflow(
        research_bundle=research_bundle,
        dataset_hash=dataset_manifest_hash,
        promotion_status=promotion.status,
    )
    if execution_bundle is not None:
        _write_execution_bundle_atomic(execution_bundle_path, execution_bundle)
    write_status_atomic(
        status_path,
        project_status(
            research_bundle,
            promotion=promotion,
            execution_bundle=execution_bundle,
        ),
    )
    return WorkflowOutcome(research_bundle, promotion, execution_bundle)


__all__ = [
    "WORKFLOW_ID",
    "WorkflowOutcome",
    "book_context_from_result",
    "build_full_research_workflow",
    "execute_research_workflow",
]
