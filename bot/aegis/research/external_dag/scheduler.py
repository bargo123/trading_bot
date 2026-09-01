"""Deterministic dependency scheduler for read-only research adapters."""
from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any

from .adapters import ResearchAdapter
from .contracts import (
    ExternalTaskRequest,
    ExternalTaskResult,
    ResearchBundle,
    WorkflowNodeSpec,
    WorkflowSpec,
    canonical_json,
    content_hash,
)
from .store import ArtifactIntegrityError, ArtifactStore


def _topological_order(workflow: WorkflowSpec) -> tuple[str, ...]:
    order_index = {node.node_id: index for index, node in enumerate(workflow.nodes)}
    remaining = {node.node_id: set(node.dependencies) for node in workflow.nodes}
    ordered: list[str] = []
    while remaining:
        ready = sorted(
            (node_id for node_id, dependencies in remaining.items() if not dependencies),
            key=order_index.__getitem__,
        )
        if not ready:
            raise ValueError("workflow dependency cycle detected")
        for node_id in ready:
            ordered.append(node_id)
            remaining.pop(node_id)
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return tuple(ordered)


class ExternalDagRunner:
    """Run ready nodes concurrently and assemble results deterministically."""

    def __init__(
        self,
        *,
        adapters: Mapping[str, ResearchAdapter],
        store: ArtifactStore,
        max_workers: int = 4,
    ) -> None:
        if int(max_workers) <= 0:
            raise ValueError("max_workers must be positive")
        self.adapters = dict(adapters)
        self.store = store
        self.max_workers = int(max_workers)

    def run(
        self,
        workflow: WorkflowSpec,
        *,
        run_id: str,
        parameters_by_node: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> ResearchBundle:
        ordered_ids = _topological_order(workflow)
        nodes = {node.node_id: node for node in workflow.nodes}
        missing_adapters = sorted(
            {node.adapter for node in workflow.nodes if node.adapter not in self.adapters}
        )
        if missing_adapters:
            raise ValueError("missing workflow adapters: " + ",".join(missing_adapters))

        parameters = dict(parameters_by_node or {})
        pending = set(ordered_ids)
        results: dict[str, ExternalTaskResult] = {}
        futures: dict[Future[ExternalTaskResult], str] = {}
        state_path = self._state_path(workflow.workflow_id, run_id)
        cached = self._load_state(state_path, workflow.workflow_id, run_id)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while pending or futures:
                progressed = False
                for node_id in ordered_ids:
                    if node_id not in pending:
                        continue
                    node = nodes[node_id]
                    if not set(node.dependencies).issubset(results):
                        continue
                    dependency_results = [results[dependency] for dependency in node.dependencies]
                    if (
                        any(result.status != "SUCCESS" for result in dependency_results)
                        and not node.allow_failed_dependencies
                    ):
                        now = time.time()
                        request = self._request(
                            workflow,
                            run_id,
                            node,
                            dependency_results,
                            parameters.get(node_id, {}),
                        )
                        results[node_id] = ExternalTaskResult(
                            request_id=request.request_id,
                            node_id=node.node_id,
                            tool_id=node.tool_id,
                            status="NOT_APPLICABLE",
                            started_at=now,
                            finished_at=now,
                            reason="dependency_not_successful",
                        )
                        pending.remove(node_id)
                        progressed = True
                        continue
                    request = self._request(
                        workflow,
                        run_id,
                        node,
                        dependency_results,
                        parameters.get(node_id, {}),
                    )
                    cached_result = cached.get(node_id)
                    if cached_result is not None and self._reusable(cached_result, request):
                        results[node_id] = cached_result
                        pending.remove(node_id)
                        progressed = True
                        continue
                    future = executor.submit(self._run_adapter, node, request)
                    futures[future] = node_id
                    pending.remove(node_id)
                    progressed = True

                if futures:
                    done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                    for future in done:
                        node_id = futures.pop(future)
                        results[node_id] = future.result()
                        self._save_state(
                            state_path,
                            workflow.workflow_id,
                            run_id,
                            results,
                        )
                    progressed = True
                if not progressed and pending:
                    raise RuntimeError("workflow scheduler made no progress")

        ordered_results = tuple(results[node_id] for node_id in ordered_ids)
        complete = all(
            results[node.node_id].status == "SUCCESS"
            for node in workflow.nodes
            if node.required
        )
        return ResearchBundle(
            workflow_id=workflow.workflow_id,
            run_id=run_id,
            node_results=ordered_results,
            complete=complete,
        )

    def _request(
        self,
        workflow: WorkflowSpec,
        run_id: str,
        node: WorkflowNodeSpec,
        dependency_results: list[ExternalTaskResult],
        parameters: Mapping[str, Any],
    ) -> ExternalTaskRequest:
        artifact_hashes = tuple(
            artifact_hash
            for result in dependency_results
            for artifact_hash in result.artifact_hashes
        )
        merged_parameters = dict(parameters)
        dataset_artifact_hash = str(
            merged_parameters.get("_dataset_artifact_hash") or ""
        ).strip().lower()
        if dataset_artifact_hash and dataset_artifact_hash not in artifact_hashes:
            artifact_hashes = (*artifact_hashes, dataset_artifact_hash)
        merged_parameters["_aegis_node_spec_hash"] = content_hash(asdict(node))
        return ExternalTaskRequest(
            workflow_id=workflow.workflow_id,
            run_id=run_id,
            node_id=node.node_id,
            tool_id=node.tool_id,
            input_artifacts=artifact_hashes,
            parameters=merged_parameters,
        )

    def _run_adapter(
        self,
        node: WorkflowNodeSpec,
        request: ExternalTaskRequest,
    ) -> ExternalTaskResult:
        started = time.time()
        try:
            return self.adapters[node.adapter].run(request, self.store)
        except Exception as exc:
            finished = time.time()
            return ExternalTaskResult(
                request_id=request.request_id,
                node_id=node.node_id,
                tool_id=node.tool_id,
                status="FAILED",
                started_at=started,
                finished_at=finished,
                reason=f"{type(exc).__name__}:{exc}",
            )

    def _state_path(self, workflow_id: str, run_id: str) -> Path:
        identity = content_hash({"workflow_id": workflow_id, "run_id": run_id})
        return self.store.root / "_runs" / f"{identity}.json"

    def _reusable(
        self,
        result: ExternalTaskResult,
        request: ExternalTaskRequest,
    ) -> bool:
        if result.status != "SUCCESS" or result.request_id != request.request_id:
            return False
        try:
            for artifact_hash in result.artifact_hashes:
                self.store.get(artifact_hash)
        except (ArtifactIntegrityError, OSError, ValueError):
            return False
        return True

    @staticmethod
    def _result_dict(result: ExternalTaskResult) -> dict[str, Any]:
        return {
            "request_id": result.request_id,
            "node_id": result.node_id,
            "tool_id": result.tool_id,
            "status": result.status,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "exit_code": result.exit_code,
            "artifact_hashes": result.artifact_hashes,
            "stdout_tail": result.stdout_tail,
            "stderr_tail": result.stderr_tail,
            "reason": result.reason,
            "payload": result.payload,
        }

    def _load_state(
        self,
        path: Path,
        workflow_id: str,
        run_id: str,
    ) -> dict[str, ExternalTaskResult]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if (
                raw.get("schema_version") != "aegis.external_dag_run_state.v1"
                or raw.get("workflow_id") != workflow_id
                or raw.get("run_id") != run_id
            ):
                return {}
            return {
                str(row["node_id"]): ExternalTaskResult(**row)
                for row in raw.get("results") or ()
            }
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _save_state(
        self,
        path: Path,
        workflow_id: str,
        run_id: str,
        results: Mapping[str, ExternalTaskResult],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": "aegis.external_dag_run_state.v1",
            "workflow_id": workflow_id,
            "run_id": run_id,
            "results": [
                self._result_dict(results[node_id])
                for node_id in sorted(results)
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(canonical_json(document))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


__all__ = ["ExternalDagRunner"]
