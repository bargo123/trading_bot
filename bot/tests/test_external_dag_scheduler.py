from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from aegis.research.external_dag import (
    ArtifactStore,
    ExternalTaskRequest,
    ExternalTaskResult,
    ExternalToolSpec,
    WorkflowNodeSpec,
    WorkflowSpec,
)
from aegis.research.external_dag.adapters import BoundedProcessAdapter
from aegis.research.external_dag.scheduler import ExternalDagRunner


@dataclass
class RecordingAdapter:
    name: str
    delay_s: float
    timeline: dict[str, tuple[float, float]]
    lock: threading.Lock

    def run(self, request: ExternalTaskRequest, store: ArtifactStore) -> ExternalTaskResult:
        started_mono = time.monotonic()
        started = time.time()
        time.sleep(self.delay_s)
        artifact = store.put(
            producer=request.tool_id,
            schema="test.node.v1",
            payload={"node_id": request.node_id, "inputs": request.input_artifacts},
        )
        finished = time.time()
        finished_mono = time.monotonic()
        with self.lock:
            self.timeline[request.node_id] = (started_mono, finished_mono)
        return ExternalTaskResult(
            request_id=request.request_id,
            node_id=request.node_id,
            tool_id=request.tool_id,
            status="SUCCESS",
            started_at=started,
            finished_at=finished,
            artifact_hashes=(artifact.content_hash,),
        )


@dataclass
class CountingAdapter:
    name: str
    calls: dict[str, int]
    fail_first: bool = False

    def run(self, request: ExternalTaskRequest, store: ArtifactStore) -> ExternalTaskResult:
        self.calls[self.name] = self.calls.get(self.name, 0) + 1
        if self.fail_first and self.calls[self.name] == 1:
            raise RuntimeError("transient failure")
        now = time.time()
        artifact = store.put(
            producer=request.tool_id,
            schema="test.resume.v1",
            payload={"node_id": request.node_id, "call": self.calls[self.name]},
        )
        return ExternalTaskResult(
            request_id=request.request_id,
            node_id=request.node_id,
            tool_id=request.tool_id,
            status="SUCCESS",
            started_at=now,
            finished_at=time.time(),
            artifact_hashes=(artifact.content_hash,),
        )


def test_scheduler_runs_ready_nodes_concurrently_but_assembles_in_workflow_order(tmp_path):
    timeline: dict[str, tuple[float, float]] = {}
    lock = threading.Lock()
    adapters = {
        name: RecordingAdapter(name, 0.06, timeline, lock)
        for name in ("source", "book", "model", "validate")
    }
    workflow = WorkflowSpec(
        workflow_id="full.v1",
        nodes=(
            WorkflowNodeSpec("source", "catalog", "source"),
            WorkflowNodeSpec("book", "book-algorithms", "book"),
            WorkflowNodeSpec("model", "qlib", "model", dependencies=("source",)),
            WorkflowNodeSpec(
                "validate",
                "oos-lab",
                "validate",
                dependencies=("book", "model"),
            ),
        ),
    )

    bundle = ExternalDagRunner(
        adapters=adapters,
        store=ArtifactStore(tmp_path / "artifacts"),
        max_workers=4,
    ).run(workflow, run_id="run-1")

    assert bundle.complete is True
    assert [result.node_id for result in bundle.node_results] == [
        "source",
        "book",
        "model",
        "validate",
    ]
    assert timeline["source"][0] < timeline["book"][1]
    assert timeline["book"][0] < timeline["source"][1]
    assert timeline["model"][0] >= timeline["source"][1]
    assert timeline["validate"][0] >= max(
        timeline["book"][1], timeline["model"][1]
    )


def test_scheduler_rejects_dependency_cycle_before_running_adapters(tmp_path):
    workflow = WorkflowSpec(
        workflow_id="cycle.v1",
        nodes=(
            WorkflowNodeSpec("a", "tool-a", "a", dependencies=("b",)),
            WorkflowNodeSpec("b", "tool-b", "b", dependencies=("a",)),
        ),
    )

    with pytest.raises(ValueError, match="cycle"):
        ExternalDagRunner(
            adapters={},
            store=ArtifactStore(tmp_path),
        ).run(workflow, run_id="run-cycle")


def test_bounded_process_adapter_times_out_and_terminates_child_tree(tmp_path):
    child_pid_path = tmp_path / "child.pid"
    script = tmp_path / "spawn_child.py"
    script.write_text(
        "import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    spec = ExternalToolSpec(
        tool_id="timeout-tool",
        role="STRESS",
        repository_path=str(tmp_path),
        repository_sha="a" * 40,
        environment=sys.executable,
        capabilities=("failure_stress",),
        command=(sys.executable, str(script), str(child_pid_path)),
        timeout_s=0.5,
    )
    request = ExternalTaskRequest(
        workflow_id="timeout.v1",
        run_id="run-timeout",
        node_id="timeout",
        tool_id=spec.tool_id,
    )

    result = BoundedProcessAdapter(spec).run(request, ArtifactStore(tmp_path / "artifacts"))

    assert result.status == "TIMEOUT"
    assert result.reason == "process_timeout"
    assert child_pid_path.exists()
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    deadline = time.time() + 3.0
    while time.time() < deadline and _process_exists(child_pid):
        time.sleep(0.05)
    assert _process_exists(child_pid) is False


def test_new_scheduler_instance_resumes_verified_success_and_reruns_failed_node(tmp_path):
    calls: dict[str, int] = {}
    adapters = {
        "root": CountingAdapter("root", calls),
        "child": CountingAdapter("child", calls, fail_first=True),
    }
    workflow = WorkflowSpec(
        workflow_id="resume.v1",
        nodes=(
            WorkflowNodeSpec("root", "root-tool", "root"),
            WorkflowNodeSpec("child", "child-tool", "child", dependencies=("root",)),
        ),
    )
    store = ArtifactStore(tmp_path / "artifacts")

    first = ExternalDagRunner(adapters=adapters, store=store).run(
        workflow, run_id="same-run"
    )
    second = ExternalDagRunner(adapters=adapters, store=store).run(
        workflow, run_id="same-run"
    )

    assert first.complete is False
    assert second.complete is True
    assert calls == {"root": 1, "child": 2}
    assert second.node_results[0].artifact_hashes == first.node_results[0].artifact_hashes


def test_scheduler_runs_control_plane_with_failed_optional_dependency_but_stays_incomplete(tmp_path):
    class FailingAdapter:
        def run(self, request, store):
            raise RuntimeError("parity_unavailable")

    class ControlPlaneAdapter:
        def run(self, request, store):
            artifact = store.put(
                producer=request.tool_id,
                schema="test.control_plane.v1",
                payload={"read_only": True},
            )
            now = time.time()
            return ExternalTaskResult(
                request_id=request.request_id,
                node_id=request.node_id,
                tool_id=request.tool_id,
                status="SUCCESS",
                started_at=now,
                finished_at=time.time(),
                artifact_hashes=(artifact.content_hash,),
            )

    workflow = WorkflowSpec(
        workflow_id="control-plane-failure.v1",
        nodes=(
            WorkflowNodeSpec("lean", "Lean", "lean"),
            WorkflowNodeSpec(
                "control",
                "OpenAlice",
                "control",
                dependencies=("lean",),
                allow_failed_dependencies=True,
            ),
        ),
    )

    bundle = ExternalDagRunner(
        adapters={"lean": FailingAdapter(), "control": ControlPlaneAdapter()},
        store=ArtifactStore(tmp_path / "artifacts"),
    ).run(workflow, run_id="control-plane-failure")

    assert bundle.complete is False
    assert bundle.node_results[0].status == "FAILED"
    assert bundle.node_results[1].status == "SUCCESS"


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
