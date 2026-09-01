"""Immutable, versioned contracts for the external research DAG."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping


_HEX_RE = re.compile(r"^[0-9a-f]+$")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("contract contains a non-finite numeric value")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported contract value: {type(value).__name__}")


def _required_text(name: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return stable UTF-8 JSON and reject non-finite numeric evidence."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=_json_default,
        )
    except ValueError as exc:
        raise ValueError("canonical JSON contains a non-finite numeric value") from exc


def content_hash(value: Any) -> str:
    """Hash canonical JSON using SHA-256."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArtifactEnvelope:
    """One immutable artifact plus its content-derived identity."""

    producer: str
    schema: str
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    content_hash: str
    schema_version: str = "aegis.external_artifact.v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "producer", _required_text("producer", self.producer))
        object.__setattr__(self, "schema", _required_text("schema", self.schema))
        digest = str(self.content_hash).lower()
        if len(digest) != 64 or not _HEX_RE.fullmatch(digest):
            raise ValueError("content_hash must be a SHA-256 digest")
        object.__setattr__(self, "content_hash", digest)
        object.__setattr__(self, "payload", _freeze_json(self.payload))
        object.__setattr__(self, "provenance", _freeze_json(self.provenance))

    def hash_material(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "producer": self.producer,
            "schema": self.schema,
            "payload": dict(self.payload),
            "provenance": dict(self.provenance),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.hash_material(), "content_hash": self.content_hash}


@dataclass(frozen=True)
class ExternalToolSpec:
    tool_id: str
    role: str
    repository_path: str
    repository_sha: str
    environment: str
    capabilities: tuple[str, ...]
    command: tuple[str, ...]
    timeout_s: float = 60.0
    broker_authority: bool = False
    schema_version: str = "aegis.external_tool_spec.v1"

    def __post_init__(self) -> None:
        for field in ("tool_id", "role", "repository_path", "repository_sha", "environment"):
            object.__setattr__(self, field, _required_text(field, getattr(self, field)))
        capabilities = tuple(_required_text("capability", value) for value in self.capabilities)
        command = tuple(_required_text("command argument", value) for value in self.command)
        if not capabilities or len(set(capabilities)) != len(capabilities):
            raise ValueError("capabilities must be non-empty and unique")
        if not command:
            raise ValueError("command is required")
        if float(self.timeout_s) <= 0:
            raise ValueError("timeout_s must be positive")
        if self.broker_authority is not False:
            raise ValueError("external tools cannot have broker authority")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "timeout_s", float(self.timeout_s))


@dataclass(frozen=True)
class WorkflowNodeSpec:
    node_id: str
    tool_id: str
    adapter: str
    dependencies: tuple[str, ...] = ()
    required: bool = True
    allow_failed_dependencies: bool = False
    timeout_s: float = 60.0
    schema_version: str = "aegis.workflow_node_spec.v1"

    def __post_init__(self) -> None:
        for field in ("node_id", "tool_id", "adapter"):
            object.__setattr__(self, field, _required_text(field, getattr(self, field)))
        dependencies = tuple(_required_text("dependency", value) for value in self.dependencies)
        if len(set(dependencies)) != len(dependencies):
            raise ValueError("dependencies must be unique")
        if self.node_id in dependencies:
            raise ValueError("node cannot depend on itself")
        if not isinstance(self.allow_failed_dependencies, bool):
            raise ValueError("allow_failed_dependencies must be boolean")
        if float(self.timeout_s) <= 0:
            raise ValueError("timeout_s must be positive")
        object.__setattr__(self, "dependencies", dependencies)
        object.__setattr__(self, "timeout_s", float(self.timeout_s))


@dataclass(frozen=True)
class WorkflowSpec:
    workflow_id: str
    nodes: tuple[WorkflowNodeSpec, ...]
    schema_version: str = "aegis.workflow_spec.v1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "workflow_id", _required_text("workflow_id", self.workflow_id))
        nodes = tuple(self.nodes)
        identifiers = tuple(node.node_id for node in nodes)
        if not nodes:
            raise ValueError("workflow requires at least one node")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("workflow contains a duplicate node")
        unknown = sorted({dep for node in nodes for dep in node.dependencies if dep not in identifiers})
        if unknown:
            raise ValueError(f"workflow contains unknown dependencies: {','.join(unknown)}")
        object.__setattr__(self, "nodes", nodes)


@dataclass(frozen=True)
class ExternalTaskRequest:
    workflow_id: str
    run_id: str
    node_id: str
    tool_id: str
    input_artifacts: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = MappingProxyType({})
    schema_version: str = "aegis.external_task_request.v1"
    request_id: str = ""

    def __post_init__(self) -> None:
        for field in ("workflow_id", "run_id", "node_id", "tool_id"):
            object.__setattr__(self, field, _required_text(field, getattr(self, field)))
        artifacts = tuple(sorted(str(value).lower() for value in self.input_artifacts))
        if len(set(artifacts)) != len(artifacts):
            raise ValueError("input_artifacts must be unique")
        if any(len(value) != 64 or not _HEX_RE.fullmatch(value) for value in artifacts):
            raise ValueError("input_artifacts must contain SHA-256 digests")
        parameters = _freeze_json(self.parameters)
        material = {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "node_id": self.node_id,
            "tool_id": self.tool_id,
            "input_artifacts": artifacts,
            "parameters": parameters,
        }
        object.__setattr__(self, "input_artifacts", artifacts)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "request_id", content_hash(material))


TERMINAL_TASK_STATUSES = frozenset(
    {"SUCCESS", "FAILED", "TIMEOUT", "UNAVAILABLE", "NOT_APPLICABLE", "INTERRUPTED"}
)


@dataclass(frozen=True)
class ExternalTaskResult:
    request_id: str
    node_id: str
    tool_id: str
    status: str
    started_at: float
    finished_at: float
    exit_code: int | None = None
    artifact_hashes: tuple[str, ...] = ()
    stdout_tail: tuple[str, ...] = ()
    stderr_tail: tuple[str, ...] = ()
    reason: str = ""
    payload: Mapping[str, Any] = MappingProxyType({})
    schema_version: str = "aegis.external_task_result.v1"

    def __post_init__(self) -> None:
        for field in ("request_id", "node_id", "tool_id"):
            object.__setattr__(self, field, _required_text(field, getattr(self, field)))
        status = str(self.status or "").upper()
        if status not in TERMINAL_TASK_STATUSES:
            raise ValueError("invalid terminal status")
        started = float(self.started_at)
        finished = float(self.finished_at)
        if not math.isfinite(started) or not math.isfinite(finished) or finished < started:
            raise ValueError("task timestamps are invalid")
        artifacts = tuple(str(value).lower() for value in self.artifact_hashes)
        if any(len(value) != 64 or not _HEX_RE.fullmatch(value) for value in artifacts):
            raise ValueError("artifact_hashes must contain SHA-256 digests")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "finished_at", finished)
        object.__setattr__(self, "artifact_hashes", artifacts)
        object.__setattr__(self, "stdout_tail", tuple(str(value) for value in self.stdout_tail))
        object.__setattr__(self, "stderr_tail", tuple(str(value) for value in self.stderr_tail))
        object.__setattr__(self, "payload", _freeze_json(self.payload))

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at) * 1000.0


@dataclass(frozen=True)
class ResearchBundle:
    workflow_id: str
    run_id: str
    node_results: tuple[ExternalTaskResult, ...]
    complete: bool
    bundle_hash: str = ""
    schema_version: str = "aegis.research_bundle.v1"

    def __post_init__(self) -> None:
        for field in ("workflow_id", "run_id"):
            object.__setattr__(self, field, _required_text(field, getattr(self, field)))
        results = tuple(self.node_results)
        node_ids = tuple(result.node_id for result in results)
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("research bundle contains duplicate node results")
        material = {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
            "complete": bool(self.complete),
            "nodes": [
                {
                    "request_id": result.request_id,
                    "node_id": result.node_id,
                    "tool_id": result.tool_id,
                    "status": result.status,
                    "artifact_hashes": result.artifact_hashes,
                    "reason": result.reason,
                }
                for result in results
            ],
        }
        digest = content_hash(material)
        if self.bundle_hash and str(self.bundle_hash) != digest:
            raise ValueError("research bundle hash mismatch")
        object.__setattr__(self, "node_results", results)
        object.__setattr__(self, "complete", bool(self.complete))
        object.__setattr__(self, "bundle_hash", digest)


__all__ = [
    "ArtifactEnvelope",
    "ExternalTaskRequest",
    "ExternalTaskResult",
    "ExternalToolSpec",
    "ResearchBundle",
    "TERMINAL_TASK_STATUSES",
    "WorkflowNodeSpec",
    "WorkflowSpec",
    "canonical_json",
    "content_hash",
]
