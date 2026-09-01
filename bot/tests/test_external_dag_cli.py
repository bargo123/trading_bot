from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

import pytest

from aegis.research.external_dag.adapters import BookAlgorithmAdapter
from aegis.research.external_dag.catalog import REQUIRED_EXTERNAL_TOOLS
from aegis.research.external_dag.contracts import (
    ExternalTaskRequest,
    ExternalTaskResult,
    content_hash,
)
from aegis.research.external_dag.orchestrator import (
    build_full_research_workflow,
    execute_research_workflow,
    book_context_from_result,
)
from aegis.research.external_dag.store import ArtifactStore
from aegis.research.watcher_algorithms import ALGORITHM_MODULES
from scripts.run_external_research_dag import main


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RecordingAdapter:
    broker_authority = False

    def __init__(
        self,
        tool_id: str,
        calls: list[str],
        input_artifacts: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.tool_id = tool_id
        self.calls = calls
        self.input_artifacts = input_artifacts

    def run(self, request, store: ArtifactStore) -> ExternalTaskResult:
        self.calls.append(self.tool_id)
        if self.input_artifacts is not None:
            self.input_artifacts[self.tool_id] = tuple(request.input_artifacts)
        artifact = store.put(
            producer=self.tool_id,
            schema="test.external_node.v1",
            payload={
                "tool_id": self.tool_id,
                "inputs": list(request.input_artifacts),
                "broker_authority": False,
            },
        )
        now = time.time()
        return ExternalTaskResult(
            request_id=request.request_id,
            node_id=request.node_id,
            tool_id=request.tool_id,
            status="SUCCESS",
            started_at=now,
            finished_at=now,
            artifact_hashes=(artifact.content_hash,),
        )


def _dataset_manifest(path: Path, *, execution_candidate: bool = False) -> None:
    evidence = {
        "target_definition": "captured_exit_replay",
        "dataset_hash": "a" * 64,
        "validation_hash": "b" * 64,
        "model_artifact_hash": "c" * 64,
        "created_at": 1_700_000_000.0,
        "expires_at": 4_100_000_000.0,
        "authorized_symbols": ["EURUSD"],
        "authorized_horizons_s": [3],
        "book_algorithm_count": 616,
        "book_registry_hash": "d" * 64,
        "chronological_test": {"expectancy": -0.01, "profit_factor": 0.9, "n_trades": 80, "n_losses": 20},
        "sealed_oos": {"expectancy": -0.01, "profit_factor": 0.9, "n_trades": 40, "n_losses": 10},
        "calibration_ece": 0.1,
        "p95_loss": 0.1,
        "p99_loss": 0.2,
        "abstain_rate": 0.5,
        "perturbation_status": "UNSTABLE",
        "replay_parity_status": "DISAGREEMENT",
        "models": {},
    }
    path.write_text(
        json.dumps(
            {
                "schema": "aegis.frozen_dataset_manifest.v1",
                "point_in_time_state": {"symbol": "EURUSD", "side": "BUY"},
                "validation_evidence": evidence,
            }
        ),
        encoding="utf-8",
    )


def test_dry_run_resolves_all_tools_book_node_and_never_starts_process(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "dataset.json"
    _dataset_manifest(manifest)
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("dry-run spawned")),
    )
    exit_code = main(
        [
            "--dry-run",
            "--dataset-manifest",
            str(manifest),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--registry",
            str(tmp_path / "experiments.sqlite"),
            "--status-path",
            str(tmp_path / "status.json"),
            "--timeout-s",
            "7.5",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["workflow_id"] == "full_research_validation.v1"
    assert set(payload["external_tools"]) == REQUIRED_EXTERNAL_TOOLS
    assert payload["book_algorithm_node"] == "aegis-book-algorithms"
    assert len(payload["nodes"]) == 15
    assert all(node["broker_authority"] is False for node in payload["nodes"])
    assert all(node["timeout_s"] == 7.5 for node in payload["nodes"])


def test_fake_end_to_end_runs_all_nodes_books_last_control_plane_and_stays_shadow(tmp_path):
    manifest = tmp_path / "dataset.json"
    _dataset_manifest(manifest)
    workflow = build_full_research_workflow()
    calls: list[str] = []
    seen_inputs: dict[str, tuple[str, ...]] = {}
    adapters = {
        tool: RecordingAdapter(tool, calls, seen_inputs)
        for tool in REQUIRED_EXTERNAL_TOOLS
    }
    adapters["aegis-book-algorithms"] = BookAlgorithmAdapter()

    outcome = execute_research_workflow(
        project_root=PROJECT_ROOT,
        dataset_manifest_path=manifest,
        run_id="fake-run",
        artifact_root=tmp_path / "artifacts",
        registry_path=tmp_path / "experiments.sqlite",
        status_path=tmp_path / "status.json",
        execution_bundle_path=tmp_path / "execution_bundle.json",
        adapters=adapters,
        max_workers=4,
    )

    assert outcome.research_bundle.complete is True
    assert len(outcome.research_bundle.node_results) == 15
    assert calls[-1] == "OpenAlice"
    assert outcome.promotion.status == "SHADOW_ONLY"
    assert outcome.execution_bundle is None
    assert not (tmp_path / "execution_bundle.json").exists()
    status = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert status["book_algorithm_count"] == 616
    assert status["promotion_status"] == "SHADOW_ONLY"
    assert len(status["nodes"]) == 15
    assert len(seen_inputs) == 14
    assert all(seen_inputs[tool] for tool in REQUIRED_EXTERNAL_TOOLS)
    common_inputs = set.intersection(
        *(set(seen_inputs[tool]) for tool in REQUIRED_EXTERNAL_TOOLS)
    )
    assert len(common_inputs) == 1


def test_book_artifact_is_compiled_into_prediction_context(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    request = ExternalTaskRequest(
        workflow_id="full_research_validation.v1",
        run_id="book-context",
        node_id="book-algorithms",
        tool_id="aegis-book-algorithms",
        input_artifacts=(),
        parameters={"state": {"symbol": "EURUSD", "decision_ts": "2026-08-31T00:00:00Z"}},
    )
    result = BookAlgorithmAdapter().run(request, store)

    context = book_context_from_result(result, store)

    assert context["algorithm_count"] == 616
    assert set(context["algorithm_ids"]) == set(context["supporting_algorithms"]) | set(context["opposing_algorithms"]) | set(context["missing_data_algorithms"])
    assert context["state_hash"]
    assert context["execution_authority"] is False
    assert context["research_only"] is True
    assert context["no_lookahead"] is True


def test_book_artifact_with_missing_rows_is_rejected_before_prediction_context(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    payload = {
        "algorithm_count": len(ALGORITHM_MODULES),
        "algorithm_ids": list(ALGORITHM_MODULES),
        "state_hash": "a" * 64,
        "algorithms": [],
        "execution_authority": False,
        "research_only": True,
        "order_intent": False,
        "no_lookahead": True,
    }
    artifact = store.put(
        producer="aegis-book-algorithms",
        schema="aegis.book_algorithm_results.v1",
        payload=payload,
        provenance={
            "module": "aegis.research.watcher_algorithms",
            "registry_hash": content_hash(tuple(ALGORITHM_MODULES)),
        },
    )
    result = ExternalTaskResult(
        request_id="book-invalid",
        node_id="book-algorithms",
        tool_id="aegis-book-algorithms",
        status="SUCCESS",
        started_at=1.0,
        finished_at=1.0,
        artifact_hashes=(artifact.content_hash,),
    )

    with pytest.raises(ValueError, match="coverage"):
        book_context_from_result(result, store)


def test_workflow_global_dependencies_put_openalice_after_every_research_node():
    workflow = build_full_research_workflow()
    by_id = {node.node_id: node for node in workflow.nodes}
    control = by_id["control-plane-status"]
    assert set(control.dependencies) == set(by_id) - {"control-plane-status"}


def test_cli_is_directly_executable_from_bot_directory():
    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
            "scripts/run_external_research_dag.py",
            "--help",
        ],
        cwd=PROJECT_ROOT / "bot",
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert "AEGIS external research DAG" in result.stdout
