from __future__ import annotations

import json
from pathlib import Path
import sys

from aegis.research.external_dag import ArtifactStore, ExternalTaskRequest, ExternalToolSpec
from aegis.research.external_dag.adapters import (
    BoundedProcessAdapter,
    _domain_artifact_payload_reason,
    build_adapter_registry,
)
from aegis.research.external_dag.catalog import load_external_catalog


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_every_catalog_tool_has_a_role_specific_read_only_adapter():
    catalog = load_external_catalog(PROJECT_ROOT)
    adapters = build_adapter_registry(PROJECT_ROOT)

    assert set(adapters) == {tool.tool_id for tool in catalog}
    assert len(adapters) == 14
    assert len({type(adapter).__name__ for adapter in adapters.values()}) == 14
    assert all(adapter.broker_authority is False for adapter in adapters.values())
    assert all(not hasattr(adapter, "place_order") for adapter in adapters.values())
    assert all(not hasattr(adapter, "close_ticket") for adapter in adapters.values())


def test_adapter_registry_preserves_catalog_tool_identity():
    adapters = build_adapter_registry(PROJECT_ROOT)

    for tool_id, adapter in adapters.items():
        assert adapter.spec.tool_id == tool_id
        assert adapter.spec.repository_sha
        assert Path(adapter.spec.repository_path).is_dir()
        assert "AEGIS_EXTERNAL_TOOL_OK" not in " ".join(adapter.spec.command)


def test_source_catalog_adapter_emits_real_role_evidence(tmp_path):
    adapters = build_adapter_registry(PROJECT_ROOT)
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="run-source-catalog",
        node_id="source_catalog",
        tool_id="awesome-systematic-trading",
    )

    result = adapters[request.tool_id].run(request, ArtifactStore(tmp_path))

    assert result.status == "SUCCESS"
    assert result.payload["role"] == "SOURCE_CATALOG"
    assert result.payload["capabilities"] == ("source_inventory",)
    assert result.payload["repository_sha"]
    assert any(line.startswith("SOURCE_LINKS=") for line in result.stdout_tail)
    assert result.payload["broker_authority"] is False


def test_external_adapter_consumes_and_attests_versioned_input_artifact(tmp_path):
    adapters = build_adapter_registry(PROJECT_ROOT)
    store = ArtifactStore(tmp_path / "artifacts")
    dataset = store.put(
        producer="aegis-dataset-manifest",
        schema="aegis.frozen_dataset_manifest.v1",
        payload={
            "schema": "aegis.frozen_dataset_manifest.v1",
            "point_in_time_state": {"symbol": "EURUSD", "side": "BUY"},
        },
        provenance={"source": "test"},
    )
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="run-source-input",
        node_id="source_catalog",
        tool_id="awesome-systematic-trading",
        input_artifacts=(dataset.content_hash,),
        parameters={"dataset_manifest_hash": dataset.content_hash},
    )

    result = adapters[request.tool_id].run(request, store)

    assert result.status == "SUCCESS"
    assert result.payload["input_artifacts_verified"] is True
    assert result.payload["input_consumed"] is True
    assert result.payload["input_artifact_count"] == 1
    assert result.payload["input_manifest_hash"] == dataset.content_hash
    assert result.payload["input_dataset_schema"] == "aegis.frozen_dataset_manifest.v1"
    assert result.payload["input_state_field_count"] == 2


def test_domain_tool_success_requires_genuine_selected_candidate_artifact(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    dataset = store.put(
        producer="aegis-dataset-manifest",
        schema="aegis.frozen_dataset_manifest.v1",
        payload={
            "schema": "aegis.frozen_dataset_manifest.v1",
            "point_in_time_state": {"symbol": "EURUSD"},
        },
        provenance={"source": "test"},
    )
    ids = ["bollinger_bands", "support_resistance"]
    marker = {
        "schema": "aegis.external_domain_artifact.v1",
        "tool": "ordersim",
        "operation": "candidate_execution_replay",
        "selected_strategy_ids": ids,
        "selected_strategy_count": len(ids),
        "domain_operation": True,
        "profitability_evidence": False,
        "artifact": {"replay_count": len(ids)},
    }
    spec = ExternalToolSpec(
        tool_id="ordersim",
        role="REPLAY",
        repository_path=str(tmp_path),
        repository_sha="a" * 40,
        environment=sys.executable,
        capabilities=("candidate_execution_replay",),
        command=(
            sys.executable,
            "-c",
            "import os; print('AEGIS_INPUT_CONSUMED=1'); "
            f"print('AEGIS_DOMAIN_ARTIFACT_JSON='+{json.dumps(marker)!r})",
        ),
    )
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="domain-marker",
        node_id="order-replay",
        tool_id="ordersim",
        input_artifacts=(dataset.content_hash,),
        parameters={
            "dataset_manifest_hash": dataset.content_hash,
            "selected_strategy_ids": ids,
        },
    )
    result = BoundedProcessAdapter(spec).run(request, store)
    # A marker that merely names the operation and strategy IDs is not a
    # domain result.  The payload must contain operation-specific replay
    # evidence before the DAG can treat the node as verified.
    assert result.status == "FAILED"
    assert result.reason == "domain_artifact_payload_incomplete"
    assert result.payload["domain_artifact_verified"] is False
    assert result.payload["domain_artifact_operation"] == "candidate_execution_replay"
    assert result.payload["selected_strategy_ids"] == tuple(ids)


def test_domain_tool_probe_without_artifact_is_rejected(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    dataset = store.put(
        producer="aegis-dataset-manifest",
        schema="aegis.frozen_dataset_manifest.v1",
        payload={
            "schema": "aegis.frozen_dataset_manifest.v1",
            "point_in_time_state": {"symbol": "EURUSD"},
        },
        provenance={"source": "test"},
    )
    spec = ExternalToolSpec(
        tool_id="ordersim",
        role="REPLAY",
        repository_path=str(tmp_path),
        repository_sha="b" * 40,
        environment=sys.executable,
        capabilities=("candidate_execution_replay",),
        command=(sys.executable, "-c", "print('AEGIS_INPUT_CONSUMED=1')"),
    )
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="domain-missing",
        node_id="order-replay",
        tool_id="ordersim",
        input_artifacts=(dataset.content_hash,),
        parameters={
            "dataset_manifest_hash": dataset.content_hash,
            "selected_strategy_ids": ["bollinger_bands"],
        },
    )
    result = BoundedProcessAdapter(spec).run(request, store)
    assert result.status == "FAILED"
    assert result.reason == "domain_artifact_missing"
    assert result.payload["domain_artifact_verified"] is False


def test_oos_domain_artifact_requires_walk_forward_cpcv_and_pbo_evidence():
    artifact = {
        "candidate_metrics": [
            {
                "strategy_id": "bollinger_bands",
                "sharpe": 0.1,
                "walk_forward_test_sharpe": [0.1, 0.2],
                "cpcv_test_sharpe": [0.1] * 6,
            }
        ],
        "pbo": 0.5,
        "pbo_splits": 6,
        "chronological_input": True,
        "not_profitability_evidence": True,
        "metrics_executed": [
            "sharpe_ratio",
            "walk_forward",
            "combinatorial_purged_kfold",
            "probability_of_backtest_overfit",
        ],
        "walk_forward": {
            "train_size": 8,
            "test_size": 4,
            "split_count": 2,
            "anchored": True,
        },
        "cpcv": {
            "n_splits": 4,
            "n_test_splits": 2,
            "embargo_pct": 0.1,
            "split_count": 6,
            "paths": 3,
        },
    }
    marker = {
        "tool": "oos-lab",
        "selected_strategy_ids": ["bollinger_bands"],
        "input_data_kind": "selected_candidate_replay_trace",
        "artifact": artifact,
    }
    assert _domain_artifact_payload_reason(marker) is None
    del artifact["cpcv"]
    assert _domain_artifact_payload_reason(marker) == "domain_artifact_payload_incomplete"
