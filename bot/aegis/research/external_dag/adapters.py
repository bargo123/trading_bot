"""Read-only adapters used by the external research DAG."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from typing import Any, Protocol
import time

from aegis.research.watcher_algorithms import ALGORITHM_MODULES, evaluate_all

from .contracts import (
    ExternalTaskRequest,
    ExternalTaskResult,
    ExternalToolSpec,
    canonical_json,
    content_hash,
)
from .catalog import (
    DOMAIN_ARTIFACT_OPERATIONS,
    DOMAIN_ARTIFACT_TOOLS,
    load_external_catalog,
)
from .store import ArtifactStore


class ResearchAdapter(Protocol):
    def run(self, request: ExternalTaskRequest, store: ArtifactStore) -> ExternalTaskResult: ...


class BookCoverageError(ValueError):
    """Raised when the adapter does not evaluate the authoritative registry."""


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _nonnegative_integer(value: Any) -> bool:
    return _finite_number(value) and float(value).is_integer() and int(value) >= 0


def _positive_integer(value: Any) -> bool:
    return _finite_number(value) and float(value).is_integer() and int(value) > 0


def _candidate_rows_match(
    rows: Any,
    selected_strategy_ids: tuple[str, ...],
    required: tuple[str, ...],
) -> bool:
    if not isinstance(rows, list) or len(rows) != len(selected_strategy_ids):
        return False
    observed: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            return False
        observed.append(str(row.get("strategy_id") or ""))
        if any(field not in row for field in required):
            return False
    return observed == list(selected_strategy_ids)


def _domain_artifact_payload_reason(
    domain_artifact: Mapping[str, Any],
) -> str | None:
    """Reject operation markers that do not contain domain-specific evidence."""
    tool = str(domain_artifact.get("tool") or "")
    names = tuple(str(value) for value in domain_artifact.get("selected_strategy_ids") or ())
    payload = domain_artifact.get("artifact")
    if not isinstance(payload, Mapping):
        return "domain_artifact_payload_incomplete"

    # Selected-strategy domain workers must consume the bounded causal replay
    # trace.  A package operation over an unlabeled/synthetic fixture is not
    # evidence for the selected AEGIS candidates.  OpenAlice is intentionally
    # exempt because its role is read-only workflow status and approvals.
    if (
        tool in DOMAIN_ARTIFACT_TOOLS
        and tool != "OpenAlice"
        and domain_artifact.get("input_data_kind") != "selected_candidate_replay_trace"
    ):
        return "domain_artifact_payload_incomplete"

    if tool == "qlib":
        if (
            payload.get("qlib_model_base") is not True
            or payload.get("model_fitted") is not True
            or payload.get("feature_artifact") is not True
            or not isinstance(payload.get("feature_names"), list)
            or not payload.get("feature_names")
            or not isinstance(payload.get("coefficients"), list)
            or len(payload["coefficients"]) != len(payload["feature_names"])
            or not all(_finite_number(value) for value in payload["coefficients"])
            or not _positive_integer(payload.get("train_rows"))
            or not _positive_integer(payload.get("test_rows"))
            or not _positive_integer(payload.get("prediction_rows"))
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "ordersim":
        rows = payload.get("candidate_replays")
        if (
            not _candidate_rows_match(rows, names, ("fills", "order_events", "final_position", "net_realized_pnl"))
            or payload.get("replay_count") != len(names)
            or payload.get("costs_included") is not True
            or any(
                not _nonnegative_integer(row.get("fills"))
                or not _nonnegative_integer(row.get("order_events"))
                or not _finite_number(row.get("final_position"))
                or not _finite_number(row.get("net_realized_pnl"))
                for row in rows
            )
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "hftbacktest":
        rows = payload.get("candidate_replays")
        if (
            not _candidate_rows_match(rows, names, ("market_events", "order_submitted", "order_response_received", "position"))
            or payload.get("replay_count") != len(names)
            or not str(payload.get("latency_model") or "").strip()
            or any(
                not _positive_integer(row.get("market_events"))
                or not isinstance(row.get("order_submitted"), bool)
                or not isinstance(row.get("order_response_received"), bool)
                or not _finite_number(row.get("position"))
                for row in rows
            )
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "oos-lab":
        rows = payload.get("candidate_metrics")
        walk_forward = payload.get("walk_forward")
        cpcv = payload.get("cpcv")
        if not isinstance(walk_forward, Mapping) or not isinstance(cpcv, Mapping):
            return "domain_artifact_payload_incomplete"
        wf_train = walk_forward.get("train_size")
        wf_test = walk_forward.get("test_size")
        wf_splits = walk_forward.get("split_count")
        if (
            not _positive_integer(wf_train)
            or not _positive_integer(wf_test)
            or not _positive_integer(wf_splits)
            or not isinstance(walk_forward.get("anchored"), bool)
        ):
            return "domain_artifact_payload_incomplete"
        cpcv_splits = cpcv.get("n_splits")
        cpcv_test_splits = cpcv.get("n_test_splits")
        cpcv_embargo = cpcv.get("embargo_pct")
        cpcv_count = cpcv.get("split_count")
        cpcv_paths = cpcv.get("paths")
        if (
            not _positive_integer(cpcv_splits)
            or int(cpcv_splits) < 2
            or not _positive_integer(cpcv_test_splits)
            or int(cpcv_test_splits) >= int(cpcv_splits)
            or not _finite_number(cpcv_embargo)
            or float(cpcv_embargo) < 0.0
            or float(cpcv_embargo) >= 1.0
            or not _positive_integer(cpcv_count)
            or int(cpcv_count) != math.comb(int(cpcv_splits), int(cpcv_test_splits))
            or not _positive_integer(cpcv_paths)
            or int(cpcv_paths) != math.comb(int(cpcv_splits) - 1, int(cpcv_test_splits) - 1)
        ):
            return "domain_artifact_payload_incomplete"
        if (
            not _candidate_rows_match(
                rows,
                names,
                ("sharpe", "walk_forward_test_sharpe", "cpcv_test_sharpe"),
            )
            or not all(_finite_number(row.get("sharpe")) for row in rows)
            or not all(
                isinstance(row.get("walk_forward_test_sharpe"), list)
                and len(row["walk_forward_test_sharpe"]) == int(wf_splits)
                and all(_finite_number(value) for value in row["walk_forward_test_sharpe"])
                and isinstance(row.get("cpcv_test_sharpe"), list)
                and len(row["cpcv_test_sharpe"]) == int(cpcv_count)
                and all(_finite_number(value) for value in row["cpcv_test_sharpe"])
                for row in rows
            )
            or not _finite_number(payload.get("pbo"))
            or not _positive_integer(payload.get("pbo_splits"))
            or payload.get("chronological_input") is not True
            or payload.get("not_profitability_evidence") is not True
            or not isinstance(payload.get("metrics_executed"), list)
            or not {
                "sharpe_ratio",
                "walk_forward",
                "combinatorial_purged_kfold",
                "probability_of_backtest_overfit",
            }.issubset(payload["metrics_executed"])
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "Keystone":
        rows = payload.get("candidate_metrics")
        if (
            not _candidate_rows_match(rows, names, ("sharpe", "max_drawdown", "deflated_sharpe"))
            or not all(
                _finite_number(row.get(field))
                for row in rows
                for field in ("sharpe", "max_drawdown", "deflated_sharpe")
            )
            or payload.get("candidate_count") != len(names)
            or payload.get("statistical_functions_executed") is not True
            or not isinstance(payload.get("metrics_executed"), list)
            or not {"sharpe_ratio", "max_drawdown", "deflated_sharpe_ratio"}.issubset(payload["metrics_executed"])
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "samvid-trading-core":
        if (
            payload.get("reconciliation_checks") != len(names)
            or payload.get("valid_open_trade_rows") != len(names)
            or payload.get("invalid_rows_rejected") != len(names)
            or payload.get("recovery_paths_exercised") != len(names)
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool in {"nautilus_trader", "Lean"}:
        if (
            not _positive_integer(payload.get("bar_count"))
            or payload.get("processed_bars") != payload.get("bar_count")
            or payload.get("candidate_count") != len(names)
            or payload.get("parity_match") is not True
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "abides":
        if (
            not _positive_integer(payload.get("sample_count"))
            or not all(_finite_number(payload.get(field)) for field in ("latency_min", "latency_max", "latency_p50", "latency_p95"))
            or float(payload.get("latency_min")) < 0.0
            or float(payload.get("latency_max")) < float(payload.get("latency_min"))
            or payload.get("disconnect_latency") != -1
            or payload.get("candidate_count") != len(names)
        ):
            return "domain_artifact_payload_incomplete"
        return None

    if tool == "OpenAlice":
        reports = payload.get("reports")
        approvals = payload.get("approvals")
        if (
            payload.get("read_only") is not True
            or not isinstance(payload.get("runtime_status"), Mapping)
            or not str(payload.get("workflow_status") or "").strip()
            or not isinstance(approvals, Mapping)
            or approvals.get("execution_bundle") is not False
            or approvals.get("mt5_demo") is not False
            or not isinstance(reports, list)
            or [str(row.get("strategy_id") or "") for row in reports if isinstance(row, Mapping)] != list(names)
            or any(not isinstance(row, Mapping) or row.get("status") != "read-only" for row in reports)
        ):
            return "domain_artifact_payload_incomplete"
        return None

    return "domain_artifact_payload_incomplete"


def _resolve_input_metadata(
    request: ExternalTaskRequest,
    store: ArtifactStore,
) -> dict[str, Any]:
    """Verify the frozen dataset artifact and return its immutable metadata."""
    if not request.input_artifacts:
        return {}
    artifacts: list[dict[str, str]] = []
    manifest_hash = str(request.parameters.get("dataset_manifest_hash") or "").lower()
    manifest_seen = False
    manifest_payload: Mapping[str, Any] | None = None
    for artifact_hash in request.input_artifacts:
        artifact = store.get(artifact_hash)
        normalized_hash = str(artifact_hash).lower()
        artifacts.append(
            {
                "hash": normalized_hash,
                "producer": artifact.producer,
                "schema": artifact.schema,
            }
        )
        if normalized_hash == manifest_hash:
            manifest_seen = artifact.schema == "aegis.frozen_dataset_manifest.v1"
            if manifest_seen:
                manifest_payload = artifact.payload
        elif (
            artifact.schema == "aegis.frozen_dataset_manifest.v1"
            and (
                not manifest_hash
                or str(artifact.provenance.get("manifest_hash") or "").lower()
                == manifest_hash
            )
        ):
            manifest_hash = normalized_hash
            manifest_seen = True
            manifest_payload = artifact.payload
    if not manifest_seen or not isinstance(manifest_payload, Mapping):
        raise ValueError("dataset manifest input is missing or invalid")
    if str(manifest_payload.get("schema") or "") != "aegis.frozen_dataset_manifest.v1":
        raise ValueError("dataset manifest payload schema is invalid")
    if not isinstance(manifest_payload.get("point_in_time_state"), Mapping):
        raise ValueError("dataset manifest point-in-time state is invalid")
    return {
        "dataset_manifest_hash": manifest_hash,
        "dataset_manifest_payload": manifest_payload,
        "artifacts": tuple(artifacts),
    }


class BookAlgorithmAdapter:
    """Evaluate every implemented book algorithm against one causal state."""

    tool_id = "aegis-book-algorithms"

    def run(self, request: ExternalTaskRequest, store: ArtifactStore) -> ExternalTaskResult:
        started = time.time()
        raw_state = request.parameters.get("state")
        if not isinstance(raw_state, Mapping):
            raise ValueError("book adapter requires a mapping state")
        state = dict(raw_state)
        input_metadata = _resolve_input_metadata(request, store)
        if input_metadata:
            manifest_state = dict(
                input_metadata["dataset_manifest_payload"]["point_in_time_state"]
            )
            if content_hash(manifest_state) != content_hash(state):
                raise ValueError("book state differs from frozen dataset state")
        evaluated = [dict(row) for row in evaluate_all(state)]
        identifiers = tuple(str(row.get("algorithm_id") or "") for row in evaluated)
        if len(identifiers) != len(ALGORITHM_MODULES) or set(identifiers) != set(ALGORITHM_MODULES):
            raise BookCoverageError("book algorithm registry coverage mismatch")

        rows: list[dict[str, Any]] = []
        for row in evaluated:
            normalized = dict(row)
            if normalized.get("execution_authority") is not False:
                raise BookCoverageError("book algorithm claimed execution authority")
            if normalized.get("research_only") is not True:
                raise BookCoverageError("book algorithm violated research-only contract")
            if normalized.get("uses_future_data") is not False:
                raise BookCoverageError("book algorithm used future data")
            rows.append(normalized)

        state_hash = content_hash(state)
        payload = {
            "algorithm_count": len(rows),
            "algorithm_ids": tuple(identifiers),
            "state_hash": state_hash,
            "decision_ts": state.get("decision_ts"),
            "algorithms": rows,
            "execution_authority": False,
            "research_only": True,
            "order_intent": False,
            "no_lookahead": True,
            "input_contract_applicable": bool(input_metadata),
            "input_artifacts_verified": bool(input_metadata),
            "input_consumed": bool(input_metadata),
            "input_artifact_count": len(input_metadata.get("artifacts", ())),
            "input_manifest_hash": input_metadata.get("dataset_manifest_hash"),
            "input_dataset_schema": (
                "aegis.frozen_dataset_manifest.v1" if input_metadata else None
            ),
            "input_state_field_count": len(state) if input_metadata else 0,
            "input_schemas": tuple(
                item["schema"] for item in input_metadata.get("artifacts", ())
            ),
        }
        artifact = store.put(
            producer=self.tool_id,
            schema="aegis.book_algorithm_results.v1",
            payload=payload,
            provenance={
                "module": "aegis.research.watcher_algorithms",
                "registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
                "request_id": request.request_id,
            },
        )
        finished = time.time()
        return ExternalTaskResult(
            request_id=request.request_id,
            node_id=request.node_id,
            tool_id=request.tool_id,
            status="SUCCESS",
            started_at=started,
            finished_at=finished,
            artifact_hashes=(artifact.content_hash,),
            payload=payload,
        )


class BoundedProcessAdapter:
    """Run one explicit read-only command with bounded output and lifetime."""

    _ENV_ALLOWLIST = (
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
    )

    def __init__(self, spec: ExternalToolSpec, *, output_line_limit: int = 200) -> None:
        self.spec = spec
        self.output_line_limit = max(1, int(output_line_limit))

    def run(self, request: ExternalTaskRequest, store: ArtifactStore) -> ExternalTaskResult:
        if request.tool_id != self.spec.tool_id:
            raise ValueError("request tool_id does not match adapter")
        working_directory = Path(self.spec.repository_path).resolve()
        if not working_directory.is_dir():
            now = time.time()
            return ExternalTaskResult(
                request_id=request.request_id,
                node_id=request.node_id,
                tool_id=request.tool_id,
                status="UNAVAILABLE",
                started_at=now,
                finished_at=now,
                reason="repository_path_unavailable",
            )

        input_path, input_metadata = self._materialize_input(request, store)
        environment = {
            key: os.environ[key]
            for key in self._ENV_ALLOWLIST
            if key in os.environ
        }
        environment["PYTHONUTF8"] = "1"
        if input_path is not None:
            environment["AEGIS_TASK_INPUT_PATH"] = str(input_path)
        popen_kwargs: dict[str, Any] = {
            "args": list(self.spec.command),
            "cwd": str(working_directory),
            "env": environment,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "shell": False,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            popen_kwargs["start_new_session"] = True

        started = time.time()
        process = subprocess.Popen(**popen_kwargs)
        status = "SUCCESS"
        reason = ""
        try:
            stdout, stderr = process.communicate(timeout=self.spec.timeout_s)
            exit_code = int(process.returncode)
            if exit_code != 0:
                status = "FAILED"
                reason = "process_exit_nonzero"
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
            reason = "process_timeout"
            self._terminate_process_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=5.0)
            except subprocess.TimeoutExpired:
                # A descendant can keep the inherited pipe open even after the
                # root process is gone.  Do not let cleanup turn a bounded task
                # into an unbounded one.
                if process.poll() is None:
                    process.kill()
                stdout, stderr = "", ""
            exit_code = process.returncode
        finally:
            if input_path is not None:
                input_path.unlink(missing_ok=True)
            manifest_path = input_metadata.get("dataset_manifest_path")
            if manifest_path:
                Path(str(manifest_path)).unlink(missing_ok=True)
        finished = time.time()
        stdout_tail = self._bounded_lines(stdout)
        stderr_tail = self._bounded_lines(stderr)
        input_consumed = any(
            line.strip() == "AEGIS_INPUT_CONSUMED=1" for line in stdout_tail
        )
        if input_metadata and not input_consumed and status == "SUCCESS":
            status = "FAILED"
            reason = "input_not_consumed"
        input_dataset_schema = self._marker_value(
            stdout_tail, "AEGIS_INPUT_DATASET_SCHEMA"
        )
        input_state_fields = self._marker_value(
            stdout_tail, "AEGIS_INPUT_STATE_FIELDS"
        )
        try:
            input_state_field_count = int(input_state_fields or 0)
        except (TypeError, ValueError):
            input_state_field_count = 0
        domain_artifact = self._parse_domain_artifact(stdout_tail)
        domain_required = self.spec.tool_id in DOMAIN_ARTIFACT_TOOLS
        expected_operation = DOMAIN_ARTIFACT_OPERATIONS.get(self.spec.tool_id)
        selected_strategy_ids = tuple(
            str(value) for value in (input_metadata.get("selected_strategy_ids") or ())
        )
        domain_reason = ""
        if domain_required:
            if domain_artifact is None:
                domain_reason = "domain_artifact_missing"
            elif _domain_artifact_payload_reason(domain_artifact):
                domain_reason = "domain_artifact_payload_incomplete"
            elif expected_operation and domain_artifact.get("operation") != expected_operation:
                domain_reason = "domain_artifact_operation_mismatch"
            elif selected_strategy_ids and tuple(
                str(value) for value in (domain_artifact.get("selected_strategy_ids") or ())
            ) != selected_strategy_ids:
                domain_reason = "domain_artifact_strategy_selection_mismatch"
            elif int(domain_artifact.get("selected_strategy_count") or 0) != len(selected_strategy_ids):
                domain_reason = "domain_artifact_strategy_count_mismatch"
            if domain_reason and status == "SUCCESS":
                status = "FAILED"
                reason = domain_reason
            elif domain_reason and not reason:
                reason = domain_reason
        payload = {
            "tool_id": self.spec.tool_id,
            "role": self.spec.role,
            "capabilities": self.spec.capabilities,
            "repository_sha": self.spec.repository_sha,
            "request_id": request.request_id,
            "status": status,
            "exit_code": exit_code,
            "command_hash": content_hash(tuple(self.spec.command)),
            "input_artifacts": request.input_artifacts,
            "input_contract_applicable": bool(input_metadata),
            "input_artifacts_verified": bool(input_metadata),
            "input_consumed": bool(input_consumed),
            "input_artifact_count": len(input_metadata.get("artifacts", ())),
            "input_manifest_hash": input_metadata.get("dataset_manifest_hash"),
            "input_dataset_schema": input_dataset_schema,
            "input_state_field_count": input_state_field_count,
            "selected_strategy_ids": selected_strategy_ids,
            "selected_strategy_count": len(selected_strategy_ids),
            "domain_artifact_verified": bool(domain_required and not domain_reason and domain_artifact),
            "domain_artifact_schema": domain_artifact.get("schema") if domain_artifact else None,
            "domain_artifact_tool": domain_artifact.get("tool") if domain_artifact else None,
            "domain_artifact_operation": domain_artifact.get("operation") if domain_artifact else None,
            "domain_artifact_strategy_count": (
                int(domain_artifact.get("selected_strategy_count") or 0)
                if domain_artifact else 0
            ),
            "domain_artifact": domain_artifact,
            "input_schemas": tuple(
                item["schema"] for item in input_metadata.get("artifacts", ())
            ),
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "broker_authority": False,
        }
        artifact = store.put(
            producer=self.spec.tool_id,
            schema="aegis.external_process_result.v1",
            payload=payload,
            provenance={
                "repository_path": str(working_directory),
                "repository_sha": self.spec.repository_sha,
                "request_id": request.request_id,
            },
        )
        return ExternalTaskResult(
            request_id=request.request_id,
            node_id=request.node_id,
            tool_id=request.tool_id,
            status=status,
            started_at=started,
            finished_at=finished,
            exit_code=exit_code,
            artifact_hashes=(artifact.content_hash,),
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            reason=reason,
            payload=payload,
        )

    @staticmethod
    def _marker_value(lines: tuple[str, ...], prefix: str) -> str | None:
        marker = f"{prefix}="
        for line in lines:
            if line.startswith(marker):
                return line[len(marker) :].strip()
        return None

    @staticmethod
    def _parse_domain_artifact(lines: tuple[str, ...]) -> dict[str, Any] | None:
        marker = "AEGIS_DOMAIN_ARTIFACT_JSON="
        encoded: str | None = None
        for line in lines:
            if line.startswith(marker):
                encoded = line[len(marker) :].strip()
        if not encoded:
            return None
        try:
            value = json.loads(encoded)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        if value.get("schema") != "aegis.external_domain_artifact.v1":
            return None
        tool = str(value.get("tool") or "")
        operation = str(value.get("operation") or "")
        ids = value.get("selected_strategy_ids")
        try:
            count = int(value.get("selected_strategy_count"))
        except (TypeError, ValueError, OverflowError):
            return None
        if (
            tool not in DOMAIN_ARTIFACT_TOOLS
            or operation != DOMAIN_ARTIFACT_OPERATIONS.get(tool)
            or not isinstance(ids, list)
            or not 1 <= len(ids) <= 10
            or len(set(str(item) for item in ids)) != len(ids)
            or count != len(ids)
            or value.get("domain_operation") is not True
            or value.get("profitability_evidence") is not False
            or not isinstance(value.get("artifact"), dict)
        ):
            return None
        return value

    @staticmethod
    def _materialize_input(
        request: ExternalTaskRequest,
        store: ArtifactStore,
    ) -> tuple[Path | None, dict[str, Any]]:
        """Verify inputs and expose a short-lived versioned task envelope."""
        metadata = _resolve_input_metadata(request, store)
        if not metadata:
            return None, {}
        artifacts = metadata["artifacts"]
        manifest_hash = metadata["dataset_manifest_hash"]
        manifest_payload = metadata["dataset_manifest_payload"]
        document = {
            "schema": "aegis.external_task_input.v1",
            "request_id": request.request_id,
            "workflow_id": request.workflow_id,
            "node_id": request.node_id,
            "tool_id": request.tool_id,
            "input_artifacts": artifacts,
            "dataset_manifest_hash": manifest_hash or None,
            "dataset_manifest_path": None,
            "selected_strategy_ids": [
                str(value)
                for value in (request.parameters.get("selected_strategy_ids") or ())
            ],
            "selected_strategy_metrics": request.parameters.get(
                "selected_strategy_metrics"
            ),
        }
        input_dir = store.root / "_inputs"
        input_dir.mkdir(parents=True, exist_ok=True)
        manifest_path: Path | None = None
        if manifest_payload is not None:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=input_dir,
                prefix=f".manifest.{request.request_id}.",
                suffix=".json",
                delete=False,
            ) as manifest_handle:
                manifest_path = Path(manifest_handle.name)
                manifest_handle.write(canonical_json(dict(manifest_payload)))
                manifest_handle.flush()
                os.fsync(manifest_handle.fileno())
            document["dataset_manifest_path"] = str(manifest_path)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=input_dir,
            prefix=f".{request.request_id}.",
            suffix=".json",
            delete=False,
        ) as handle:
            input_path = Path(handle.name)
            handle.write(canonical_json(document))
            handle.flush()
            os.fsync(handle.fileno())
        return input_path, {
            "dataset_manifest_hash": manifest_hash or None,
            "artifacts": tuple(artifacts),
            "dataset_manifest_path": str(manifest_path) if manifest_path else None,
            "dataset_manifest_payload": manifest_payload,
            "selected_strategy_ids": tuple(document["selected_strategy_ids"]),
            "selected_strategy_metrics": document["selected_strategy_metrics"],
        }

    def _bounded_lines(self, value: str | None) -> tuple[str, ...]:
        lines = str(value or "").splitlines()
        return tuple(line[-4000:] for line in lines[-self.output_line_limit :])

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if os.name == "nt":
            BoundedProcessAdapter._terminate_windows_tree(int(process.pid))
            # The root handle is owned by this process; close it as a final
            # fallback if the snapshot API could not open it.
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
        else:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

    @staticmethod
    def _terminate_windows_tree(root_pid: int) -> None:
        """Terminate a process and descendants without blocking on taskkill."""
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        PROCESS_TERMINATE = 0x0001
        ULONG_PTR = ctypes.c_size_t

        class _ProcessEntry32(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ULONG_PTR),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.OpenProcess.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == INVALID_HANDLE_VALUE:
            return
        try:
            first = kernel32.Process32FirstW
            next_process = kernel32.Process32NextW
            first.restype = wintypes.BOOL
            next_process.restype = wintypes.BOOL
            first.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32)]
            next_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32)]
            entry = _ProcessEntry32()
            entry.dwSize = ctypes.sizeof(_ProcessEntry32)
            parent_of: dict[int, int] = {}
            if first(snapshot, ctypes.byref(entry)):
                while True:
                    parent_of[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                    entry = _ProcessEntry32()
                    entry.dwSize = ctypes.sizeof(_ProcessEntry32)
                    if not next_process(snapshot, ctypes.byref(entry)):
                        break
        finally:
            kernel32.CloseHandle(snapshot)

        descendants: list[int] = []
        frontier = [int(root_pid)]
        while frontier:
            parent = frontier.pop()
            children = [pid for pid, parent_pid in parent_of.items() if parent_pid == parent]
            descendants.extend(children)
            frontier.extend(children)
        for pid in reversed(descendants + [int(root_pid)]):
            handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
            if handle:
                try:
                    kernel32.TerminateProcess(handle, 1)
                finally:
                    kernel32.CloseHandle(handle)


class _RoleProcessAdapter(BoundedProcessAdapter):
    broker_authority = False


class OpenAliceControlPlaneAdapter(_RoleProcessAdapter):
    pass


class SourceCatalogAdapter(_RoleProcessAdapter):
    pass


class QlibModelAdapter(_RoleProcessAdapter):
    pass


class OrderSimReplayAdapter(_RoleProcessAdapter):
    pass


class HftBacktestReplayAdapter(_RoleProcessAdapter):
    pass


class OosLabValidationAdapter(_RoleProcessAdapter):
    pass


class KeystoneValidationAdapter(_RoleProcessAdapter):
    pass


class ResearchIntegrityAdapter(_RoleProcessAdapter):
    pass


class SamvidRecoveryAdapter(_RoleProcessAdapter):
    pass


class VibePreflightReferenceAdapter(_RoleProcessAdapter):
    pass


class Mt5ReadOnlyDiagnosticsAdapter(_RoleProcessAdapter):
    pass


class NautilusParityAdapter(_RoleProcessAdapter):
    pass


class LeanParityAdapter(_RoleProcessAdapter):
    pass


class AbidesStressAdapter(_RoleProcessAdapter):
    pass


_ROLE_ADAPTER_TYPES: dict[str, type[_RoleProcessAdapter]] = {
    "OpenAlice": OpenAliceControlPlaneAdapter,
    "awesome-systematic-trading": SourceCatalogAdapter,
    "qlib": QlibModelAdapter,
    "ordersim": OrderSimReplayAdapter,
    "hftbacktest": HftBacktestReplayAdapter,
    "oos-lab": OosLabValidationAdapter,
    "Keystone": KeystoneValidationAdapter,
    "algorithmic-trading-research-framework": ResearchIntegrityAdapter,
    "samvid-trading-core": SamvidRecoveryAdapter,
    "Vibe-Trading": VibePreflightReferenceAdapter,
    "metatrader5-mcp-server": Mt5ReadOnlyDiagnosticsAdapter,
    "nautilus_trader": NautilusParityAdapter,
    "Lean": LeanParityAdapter,
    "abides": AbidesStressAdapter,
}


def build_adapter_registry(
    project_root: str | Path,
    *,
    timeout_s: float | None = None,
) -> dict[str, ResearchAdapter]:
    """Build one explicit, broker-read-only adapter per installed tool."""
    catalog = load_external_catalog(project_root)
    return {
        spec.tool_id: _ROLE_ADAPTER_TYPES[spec.tool_id](
            replace(spec, timeout_s=float(timeout_s)) if timeout_s is not None else spec
        )
        for spec in catalog
    }


__all__ = [
    "BookAlgorithmAdapter",
    "BookCoverageError",
    "BoundedProcessAdapter",
    "build_adapter_registry",
    "ResearchAdapter",
]
