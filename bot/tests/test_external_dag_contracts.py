from __future__ import annotations

import json
import math

import pytest

from aegis.research.external_dag import (
    ArtifactIntegrityError,
    ArtifactStore,
    ExternalTaskRequest,
    ExternalTaskResult,
    ExternalToolSpec,
    WorkflowNodeSpec,
    WorkflowSpec,
    canonical_json,
    content_hash,
)


def test_canonical_hash_is_key_order_independent_and_rejects_nonfinite_values():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})

    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"value": math.inf})


def test_artifact_store_detects_payload_mutation(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = store.put(
        producer="qlib",
        schema="aegis.qlib.v1",
        payload={"feature_count": 4, "dataset_hash": "dataset-1"},
    )
    duplicate = store.put(
        producer="qlib",
        schema="aegis.qlib.v1",
        payload={"dataset_hash": "dataset-1", "feature_count": 4},
    )

    assert duplicate.content_hash == artifact.content_hash
    assert store.get(artifact.content_hash) == artifact

    path = store.path_for(artifact.content_hash)
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["payload"]["feature_count"] = 5
    path.write_text(json.dumps(saved), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError, match="content hash mismatch"):
        store.get(artifact.content_hash)


def test_contract_payloads_are_deeply_immutable(tmp_path):
    artifact = ArtifactStore(tmp_path).put(
        producer="ordersim",
        schema="aegis.replay.v1",
        payload={"costs": {"spread": 0.1}, "fills": [1, 2]},
    )

    with pytest.raises(TypeError):
        artifact.payload["costs"] = {"spread": 0.2}
    with pytest.raises(TypeError):
        artifact.payload["costs"]["spread"] = 0.2
    assert artifact.payload["fills"] == (1, 2)


def test_tool_and_workflow_contracts_reject_unsafe_or_ambiguous_identity():
    with pytest.raises(ValueError, match="broker authority"):
        ExternalToolSpec(
            tool_id="unsafe",
            role="MODEL",
            repository_path="C:/repo",
            repository_sha="a" * 40,
            environment="C:/python.exe",
            capabilities=("model",),
            command=("python", "worker.py"),
            broker_authority=True,
        )

    tool = ExternalToolSpec(
        tool_id="qlib",
        role="MODEL",
        repository_path="C:/repo",
        repository_sha="a" * 40,
        environment="C:/python.exe",
        capabilities=("model",),
        command=("python", "worker.py"),
    )
    node = WorkflowNodeSpec(
        node_id="model",
        tool_id=tool.tool_id,
        adapter="QlibAdapter",
        dependencies=("dataset",),
        timeout_s=30.0,
    )
    with pytest.raises(ValueError, match="duplicate node"):
        WorkflowSpec(workflow_id="full.v1", nodes=(node, node))


def test_task_contracts_derive_stable_request_id_and_validate_terminal_status():
    request = ExternalTaskRequest(
        workflow_id="full.v1",
        run_id="run-1",
        node_id="book",
        tool_id="aegis-book-algorithms",
        input_artifacts=("b" * 64, "a" * 64),
        parameters={"decision_ts": 10.0},
    )
    reordered = ExternalTaskRequest(
        workflow_id="full.v1",
        run_id="run-1",
        node_id="book",
        tool_id="aegis-book-algorithms",
        input_artifacts=("a" * 64, "b" * 64),
        parameters={"decision_ts": 10.0},
    )

    assert request.request_id == reordered.request_id
    with pytest.raises(ValueError, match="terminal status"):
        ExternalTaskResult(
            request_id=request.request_id,
            node_id="book",
            tool_id="aegis-book-algorithms",
            status="MAYBE",
            started_at=1.0,
            finished_at=2.0,
        )
