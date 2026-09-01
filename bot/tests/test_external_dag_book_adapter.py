from __future__ import annotations

from aegis.research.external_dag import ArtifactStore, ExternalTaskRequest
from aegis.research.external_dag.adapters import BookAlgorithmAdapter
from aegis.research.external_dag.contracts import content_hash
from aegis.research.watcher_algorithms import ALGORITHM_MODULES


def test_book_adapter_evaluates_exact_authoritative_registry(tmp_path):
    store = ArtifactStore(tmp_path)
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="run-book-1",
        node_id="book_algorithms",
        tool_id="aegis-book-algorithms",
        parameters={
            "state": {
                "symbol": "EURUSD",
                "side": "BUY",
                "decision_ts": 10.0,
            }
        },
    )

    result = BookAlgorithmAdapter().run(request, store)
    artifact = store.get(result.artifact_hashes[0])
    rows = artifact.payload["algorithms"]

    assert result.status == "SUCCESS"
    assert len(rows) == len(ALGORITHM_MODULES) == 616
    assert {row["algorithm_id"] for row in rows} == set(ALGORITHM_MODULES)
    assert all(row["execution_authority"] is False for row in rows)
    assert all(row["research_only"] is True for row in rows)
    assert all(row["uses_future_data"] is False for row in rows)


def test_book_adapter_preserves_missing_data_instead_of_fabricating_a_view(tmp_path):
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="run-book-2",
        node_id="book_algorithms",
        tool_id="aegis-book-algorithms",
        parameters={"state": {"symbol": "EURUSD", "decision_ts": 10.0}},
    )

    result = BookAlgorithmAdapter().run(request, ArtifactStore(tmp_path))
    rows = result.payload["algorithms"]

    trend = next(row for row in rows if row["algorithm_id"] == "trend_continuation")
    assert trend["applicability"] == "MISSING_DATA"
    assert trend["view"] == "MISSING_DATA"
    assert trend["missing_inputs"]


def test_book_adapter_verifies_frozen_input_state(tmp_path):
    store = ArtifactStore(tmp_path)
    state = {"symbol": "EURUSD", "side": "BUY", "decision_ts": 10.0}
    dataset = store.put(
        producer="aegis-dataset-manifest",
        schema="aegis.frozen_dataset_manifest.v1",
        payload={
            "schema": "aegis.frozen_dataset_manifest.v1",
            "point_in_time_state": state,
        },
        provenance={"manifest_hash": "a" * 64},
    )
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="run-book-input",
        node_id="book_algorithms",
        tool_id="aegis-book-algorithms",
        input_artifacts=(dataset.content_hash,),
        parameters={
            "state": state,
            "dataset_manifest_hash": dataset.content_hash,
        },
    )

    result = BookAlgorithmAdapter().run(request, store)

    assert result.payload["input_contract_applicable"] is True
    assert result.payload["input_artifacts_verified"] is True
    assert result.payload["input_consumed"] is True
    assert result.payload["input_manifest_hash"] == dataset.content_hash
    assert result.payload["input_dataset_schema"] == "aegis.frozen_dataset_manifest.v1"
    assert result.payload["input_state_field_count"] == len(state)
    assert result.payload["state_hash"] == content_hash(state)
